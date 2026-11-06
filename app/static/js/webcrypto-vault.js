/**
 * Teacher Zero-Knowledge Vault (WebCrypto AES-GCM 256-bit)
 * Zero-PII standard: Server never sees student names.
 * Keys live strictly in teacher's browser memory / localStorage.
 */

export class TeacherZeroKnowledgeVault {
  constructor(teacherId = "default") {
    this.teacherId = String(teacherId);
    this.storageKey = `bc_teacher_aes_jwk_${this.teacherId}`;
    this.cryptoKey = null;
  }

  async initOrLoadKey(passphrase = null) {
    if (passphrase) {
      const enc = new TextEncoder();
      const keyMaterial = await crypto.subtle.importKey(
        "raw",
        enc.encode(passphrase),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
      );
      this.cryptoKey = await crypto.subtle.deriveKey(
        {
          name: "PBKDF2",
          salt: enc.encode(`bormoclass-zero-pii-salt-v1-${this.teacherId}`),
          iterations: 100000,
          hash: "SHA-256",
        },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
      );
      const jwk = await crypto.subtle.exportKey("jwk", this.cryptoKey);
      localStorage.setItem(this.storageKey, JSON.stringify(jwk));
      return true;
    }

    const saved = localStorage.getItem(this.storageKey);
    if (saved) {
      try {
        this.cryptoKey = await crypto.subtle.importKey(
          "jwk",
          JSON.parse(saved),
          { name: "AES-GCM" },
          true,
          ["encrypt", "decrypt"]
        );
        return true;
      } catch (e) {
        console.warn("Failed to import saved vault key", e);
      }
    }
    return false;
  }

  hasKey() {
    return Boolean(this.cryptoKey);
  }

  async encryptStudentName(plainName) {
    if (!this.cryptoKey) throw new Error("Ключ учителя не инициализирован");
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plainName.trim());
    const cipherBuf = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, this.cryptoKey, encoded);
    const ivB64 = btoa(String.fromCharCode(...iv));
    const cipherB64 = btoa(String.fromCharCode(...new Uint8Array(cipherBuf)));
    return `${ivB64}:${cipherB64}`;
  }

  async decryptStudentName(encryptedNote) {
    if (!encryptedNote || !encryptedNote.includes(":") || !this.cryptoKey) return null;
    try {
      const [ivB64, cipherB64] = encryptedNote.split(":");
      const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0));
      const cipher = Uint8Array.from(atob(cipherB64), (c) => c.charCodeAt(0));
      const plainBuf = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, this.cryptoKey, cipher);
      return new TextDecoder().decode(plainBuf);
    } catch {
      return "🔒 [Неверный ключ]";
    }
  }

  async exportKeyJson() {
    if (!this.cryptoKey) return null;
    const jwk = await crypto.subtle.exportKey("jwk", this.cryptoKey);
    return JSON.stringify(jwk);
  }
}
