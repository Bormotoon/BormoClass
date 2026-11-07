/**
 * BormoClass Transport Client & SSE Reactive Bus
 * REST API v1 & Internal Classroom API wrapper.
 * Zero external CDN dependencies. Zero-PII compliant. 100% автономность.
 */

export class BormoAPIError extends Error {
  constructor(message, status = 500, code = 500, statusText = "ERROR", details = [], raw = null) {
    super(message);
    this.name = "BormoAPIError";
    this.status = status;
    this.code = code;
    this.statusText = statusText;
    this.details = Array.isArray(details) ? details : [];
    this.raw = raw;
  }
}
export const GoogleAPIError = BormoAPIError;

/**
 * Automatically builds comma-separated updateMask string from object keys.
 * @param {Object|Array<string>|string} maskInput
 * @returns {string}
 */
export function buildUpdateMask(maskInput) {
  if (!maskInput) return "";
  if (typeof maskInput === "string") return maskInput.trim();
  if (Array.isArray(maskInput)) return maskInput.join(",");
  if (typeof maskInput === "object") {
    return Object.keys(maskInput)
      .filter((k) => maskInput[k] !== undefined && maskInput[k] !== null)
      .join(",");
  }
  return "";
}

/**
 * Universal fetch wrapper for /v1/* and /api/classroom/* routes.
 * Handles updateMask parameter, JSON serializing and Google Error payload unwrapping.
 *
 * @param {string} path - URL or path like '/v1/courses' or '/api/classroom/classes'
 * @param {Object} options - Standard fetch options + updateMask, params
 * @returns {Promise<any>}
 */
export async function v1Fetch(path, options = {}) {
  const fetchOpts = { ...options };
  let url = path;

  // Handle URL query parameters and updateMask
  const queryParams = new URLSearchParams();

  if (fetchOpts.params && typeof fetchOpts.params === "object") {
    for (const [k, v] of Object.entries(fetchOpts.params)) {
      if (v !== undefined && v !== null) {
        queryParams.set(k, String(v));
      }
    }
  }

  // Handle updateMask
  if (fetchOpts.updateMask) {
    let maskStr = "";
    if (fetchOpts.updateMask === true && fetchOpts.body && typeof fetchOpts.body === "object") {
      maskStr = buildUpdateMask(fetchOpts.body);
    } else {
      maskStr = buildUpdateMask(fetchOpts.updateMask);
    }
    if (maskStr) {
      queryParams.set("updateMask", maskStr);
    }
  }

  const qs = queryParams.toString();
  if (qs) {
    const separator = url.includes("?") ? "&" : "?";
    url = `${url}${separator}${qs}`;
  }

  // Headers & Body setup
  const headers = { ...(fetchOpts.headers || {}) };
  const hasBody = fetchOpts.body !== undefined && fetchOpts.body !== null;

  if (hasBody && !(fetchOpts.body instanceof FormData) && typeof fetchOpts.body !== "string") {
    headers["Content-Type"] = "application/json";
    fetchOpts.body = JSON.stringify(fetchOpts.body);
  }

  fetchOpts.headers = headers;

  // Clean custom options before passing to native fetch
  delete fetchOpts.params;
  delete fetchOpts.updateMask;

  let response;
  try {
    response = await fetch(url, fetchOpts);
  } catch (netErr) {
    throw new BormoAPIError(
      `Сетевая ошибка при обращении к ${url}: ${netErr.message}`,
      0,
      0,
      "NETWORK_ERROR",
      [],
      null
    );
  }

  // 204 No Content
  if (response.status === 204) {
    return null;
  }

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.text();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let errMsg = "Ошибка при выполнении запроса";
    let errCode = response.status;
    let errStatus = response.statusText;
    let errDetails = [];

    // Parse Google REST Error format: { error: { code, message, status, details } }
    if (data && typeof data === "object") {
      if (data.error && typeof data.error === "object") {
        errMsg = data.error.message || errMsg;
        errCode = data.error.code || errCode;
        errStatus = data.error.status || errStatus;
        errDetails = data.error.details || [];
      } else if (typeof data.detail === "string") {
        errMsg = data.detail;
      } else if (Array.isArray(data.detail)) {
        errMsg = data.detail
          .map((item) => (typeof item === "object" ? item.msg || JSON.stringify(item) : String(item)))
          .join("; ");
        errDetails = data.detail;
      } else if (typeof data.message === "string") {
        errMsg = data.message;
      }
    } else if (typeof data === "string" && data.trim()) {
      errMsg = data.slice(0, 300);
    }

    if (response.status === 401) errMsg = "Требуется авторизация.";
    if (response.status === 403) errMsg = errMsg || "Доступ запрещен.";
    if (response.status === 404) errMsg = errMsg || "Запрошенный ресурс не найден.";

    throw new BormoAPIError(errMsg, response.status, errCode, errStatus, errDetails, data);
  }

  return data;
}

/**
 * Helper to fetch all pages of a paginated list endpoint using nextPageToken.
 *
 * @param {string} path - URL endpoint
 * @param {string} listKey - The JSON key holding items array (e.g. 'courses', 'courseWork')
 * @param {Object} [params] - Query parameters
 * @returns {Promise<Array<any>>} - Flat array of all accumulated items
 */
export async function fetchAllPages(path, listKey, params = {}) {
  const items = [];
  let pageToken = params.pageToken || null;
  let pageCount = 0;
  const maxPages = params.maxPages || 50;

  do {
    const pageParams = { ...params };
    delete pageParams.maxPages;
    if (pageToken) {
      pageParams.pageToken = pageToken;
    }

    const data = await v1Fetch(path, { method: "GET", params: pageParams });
    if (!data) break;

    const list = Array.isArray(data[listKey]) ? data[listKey] : [];
    items.push(...list);

    pageToken = data.nextPageToken || null;
    pageCount++;
  } while (pageToken && pageCount < maxPages);

  return items;
}

/**
 * Subscribes to Server-Sent Events stream for a specific classroom.
 *
 * @param {number|string} classId
 * @param {Function} callback - (eventName, payload, eventObj) => void
 * @param {Object} [options]
 * @returns {{ eventSource: EventSource, unsubscribe: Function }}
 */
export function subscribeClassEvents(classId, callback, options = {}) {
  const streamUrl = `/api/classroom/${classId}/stream`;
  const es = new EventSource(streamUrl);

  const eventTypes = [
    "message",
    "connected",
    "keep-alive",
    "post_created",
    "post_updated",
    "post_deleted",
    "coursework_created",
    "coursework_updated",
    "submission_updated",
    "desk_updated",
    "comment_created",
    "comment_deleted",
    "grade_updated",
    "roster_updated",
    "student_group_updated",
    "guardian_updated"
  ];

  eventTypes.forEach((evt) => {
    es.addEventListener(evt, (e) => {
      let payload = null;
      try {
        payload = e.data ? JSON.parse(e.data) : null;
      } catch {
        payload = e.data;
      }
      if (typeof callback === "function") {
        callback(evt, payload, e);
      }
    });
  });

  es.onerror = (err) => {
    if (typeof options.onError === "function") {
      options.onError(err);
    }
  };

  return {
    eventSource: es,
    unsubscribe: () => {
      try {
        es.close();
      } catch {
        // Safe ignore
      }
    }
  };
}
