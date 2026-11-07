#!/usr/bin/env python3
"""
Downloads and structures official Google Classroom documentation, API discovery specs,
guides, and architectural data models into docs/google_classroom.
"""

import json
import os
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "docs" / "google_classroom"
GUIDES_DIR = BASE_DIR / "guides"
DISCOVERY_DIR = BASE_DIR / "discovery"
REF_DIR = BASE_DIR / "reference"
ARCH_DIR = BASE_DIR / "architecture"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

GUIDES_LIST = [
    ("/workspace/classroom/guides/get-started", "get-started.md", "Get Started with Classroom API"),
    ("/workspace/classroom/guides/key-concepts/api-structure", "api-structure.md", "API Resources & Structure"),
    ("/workspace/classroom/guides/key-concepts/user-types", "user-types.md", "User Types & Roles"),
    ("/workspace/classroom/guides/key-concepts/admin-actions", "admin-actions.md", "Administrator Actions"),
    ("/workspace/classroom/guides/key-concepts/grades", "grades-concepts.md", "Grades & Grading Concepts"),
    ("/workspace/classroom/guides/key-concepts/user-eligibility", "user-eligibility.md", "User Eligibility"),
    ("/workspace/classroom/guides/manage-courses", "manage-courses.md", "Manage Courses"),
    ("/workspace/classroom/guides/manage-coursework", "manage-coursework.md", "Manage CourseWork & Materials"),
    ("/workspace/classroom/guides/manage-users", "manage-users.md", "Manage Users (Teachers & Students)"),
    ("/workspace/classroom/guides/manage-topics", "manage-topics.md", "Manage Topics"),
    ("/workspace/classroom/guides/manage-guardians", "manage-guardians.md", "Manage Guardians"),
    ("/workspace/classroom/guides/manage-invitations", "manage-invitations.md", "Manage Invitations"),
    ("/workspace/classroom/guides/manage-student-groups", "manage-student-groups.md", "Manage Student Groups"),
    ("/workspace/classroom/guides/manage-learning-goals", "manage-learning-goals.md", "Manage Learning Goals"),
    ("/workspace/classroom/guides/manage-aliases", "manage-aliases.md", "Manage Course Aliases"),
    ("/workspace/classroom/guides/classroom-api/manage-grades", "manage-grades.md", "Manage Grades & Categories"),
    ("/workspace/classroom/guides/coursework-integration", "coursework-integration.md", "CourseWork & Submission Integration"),
    ("/workspace/classroom/guides/auth", "authentication.md", "Authentication & Scopes"),
    ("/workspace/classroom/guides/onboarding/how-requests-work", "how-requests-work.md", "How API Requests Work"),
    ("/workspace/classroom/guides/onboarding/prerequisites", "prerequisites.md", "Prerequisites"),
]


class CleanMarkdownParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = []
        self.skip_stack = 0
        self.in_pre = False
        self.in_code = False
        self.current_href = ""
        self.list_level = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        # Skip headers, footers, breadcrumbs, banners, feedback
        if any(c in ["devsite-nav", "devsite-header", "devsite-footer", "devsite-banner", "nocontent", "devsite-feedback"] for c in classes) or tag in ["script", "style"]:
            self.skip_stack += 1
            return

        if self.skip_stack > 0:
            return

        if tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            lvl = int(tag[1])
            self.output.append(f"\n\n{'#' * lvl} ")
        elif tag == "p":
            self.output.append("\n\n")
        elif tag == "br":
            self.output.append("\n")
        elif tag in ["ul", "ol"]:
            self.list_level += 1
            self.output.append("\n")
        elif tag == "li":
            indent = "  " * (self.list_level - 1)
            self.output.append(f"\n{indent}- ")
        elif tag == "pre":
            self.in_pre = True
            self.output.append("\n\n```\n")
        elif tag == "code" and not self.in_pre:
            self.in_code = True
            self.output.append("`")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href.startswith("/"):
                href = "https://developers.google.com" + href
            self.current_href = href
            self.output.append("[")
        elif tag in ["b", "strong"]:
            self.output.append("**")
        elif tag in ["i", "em"]:
            self.output.append("*")
        elif tag == "tr":
            self.output.append("\n| ")
        elif tag in ["th", "td"]:
            pass

    def handle_endtag(self, tag):
        if tag in ["script", "style"] or self.skip_stack > 0:
            # Need to be cautious with tags that were skipped
            # Only decrement if this endtag corresponds to what we skipped
            # Simplified: decrement if skip_stack > 0
            if tag in ["script", "style", "devsite-nav", "devsite-header", "devsite-footer"]:
                self.skip_stack = max(0, self.skip_stack - 1)
            return

        if tag == "pre":
            self.in_pre = False
            self.output.append("\n```\n")
        elif tag == "code" and not self.in_pre:
            self.in_code = False
            self.output.append("`")
        elif tag == "a":
            if self.current_href:
                self.output.append(f"]({self.current_href})")
            else:
                self.output.append("]")
            self.current_href = ""
        elif tag in ["b", "strong"]:
            self.output.append("**")
        elif tag in ["i", "em"]:
            self.output.append("*")
        elif tag in ["th", "td"]:
            self.output.append(" | ")
        elif tag in ["ul", "ol"]:
            self.list_level = max(0, self.list_level - 1)
            self.output.append("\n")

    def handle_data(self, data):
        if self.skip_stack > 0:
            return
        self.output.append(data)


def download_discovery():
    print("Downloading Google Classroom API v1 Discovery document...")
    url = "https://classroom.googleapis.com/$discovery/rest?version=v1"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    disc_path = DISCOVERY_DIR / "classroom_v1.json"
    with open(disc_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved Discovery Document: {disc_path} ({len(data.get('schemas', {}))} schemas)")
    return data


def download_guides():
    print(f"Downloading {len(GUIDES_LIST)} guides from Google Developer documentation...")
    for path, filename, title in GUIDES_LIST:
        url = "https://developers.google.com" + path
        target_file = GUIDES_DIR / filename
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8")

            # Extract article content
            article_match = re.search(r'<article class="devsite-article">([\s\S]*?)</article>', html)
            content_html = article_match.group(1) if article_match else html

            # Clean nocontent divs before parsing
            content_html = re.sub(r'<div class="[^"]*nocontent[^"]*"[\s\S]*?</div>', '', content_html)
            content_html = re.sub(r'<devsite-content-data[\s\S]*?</devsite-content-data>', '', content_html)

            parser = CleanMarkdownParser()
            parser.feed(content_html)
            raw_md = "".join(parser.output)

            # Clean formatting
            clean_md = re.sub(r'\n{3,}', '\n\n', raw_md).strip()
            # Remove any left-over navigation text at beginning if present
            lines = clean_md.split("\n")
            # find first # heading
            first_h = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
            if first_h is not None:
                clean_md = "\n".join(lines[first_h:])

            header = f"# {title}\n\n> Source: [{url}]({url})\n\n---\n\n"
            final_md = header + clean_md

            with open(target_file, "w", encoding="utf-8") as f:
                f.write(final_md)
            print(f"  [OK] {filename}")
        except Exception as e:
            print(f"  [FAIL] {filename}: {e}")


def generate_schemas_reference(discovery_data):
    print("Generating schemas reference from discovery document...")
    schemas = discovery_data.get("schemas", {})
    target_file = REF_DIR / "schemas.md"

    lines = [
        "# Google Classroom API Data Schemas",
        "",
        "> Generated from official Google Classroom API v1 Discovery Document.",
        f"> Total Schemas: **{len(schemas)}**",
        "",
        "## Table of Contents",
        "",
    ]

    for schema_name in sorted(schemas.keys()):
        lines.append(f"- [{schema_name}](#{schema_name.lower()})")

    lines.append("\n---\n")

    for schema_name in sorted(schemas.keys()):
        schema = schemas[schema_name]
        lines.append(f"## {schema_name}")
        lines.append(f"**Type:** `{schema.get('type', 'object')}`\n")
        desc = schema.get("description", "No description provided.")
        lines.append(f"{desc}\n")

        properties = schema.get("properties", {})
        if properties:
            lines.append("| Field | Type | Format / Enum | Description |")
            lines.append("|---|---|---|---|")
            for prop_name, prop_data in properties.items():
                p_type = prop_data.get("type", prop_data.get("$ref", "any"))
                if "$ref" in prop_data:
                    p_type = f"[`{prop_data['$ref']}`](#{prop_data['$ref'].lower()})"
                elif p_type == "array":
                    items = prop_data.get("items", {})
                    ref = items.get("$ref", items.get("type", "any"))
                    p_type = f"Array of [`{ref}`](#{ref.lower()})" if "$ref" in items else f"Array of `{ref}`"

                enum_vals = prop_data.get("enum", [])
                enum_str = ", ".join(f"`{e}`" for e in enum_vals) if enum_vals else prop_data.get("format", "-")
                p_desc = prop_data.get("description", "").replace("\n", " ")
                # Truncate overly long descriptions in table
                if len(p_desc) > 300:
                    p_desc = p_desc[:297] + "..."
                lines.append(f"| `{prop_name}` | {p_type} | {enum_str} | {p_desc} |")
            lines.append("")
        lines.append("\n---\n")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved Schemas Reference: {target_file}")


def generate_endpoints_reference(discovery_data):
    print("Generating endpoints & methods reference...")
    target_file = REF_DIR / "endpoints.md"
    resources = discovery_data.get("resources", {})

    lines = [
        "# Google Classroom API REST Resources & Methods",
        "",
        "> Complete list of resources, HTTP methods, paths, and descriptions.",
        "",
    ]

    def process_resource(res_name, res_data, prefix=""):
        full_name = f"{prefix}.{res_name}" if prefix else res_name
        lines.append(f"## Resource: `{full_name}`\n")

        methods = res_data.get("methods", {})
        if methods:
            lines.append("| Method | HTTP | Path | Description |")
            lines.append("|---|---|---|---|")
            for m_name, m_data in methods.items():
                http_m = m_data.get("httpMethod", "GET")
                path = m_data.get("path", "")
                desc = m_data.get("description", "").replace("\n", " ")
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                lines.append(f"| `{m_name}` | `{http_m}` | `{path}` | {desc} |")
            lines.append("\n")

        sub_resources = res_data.get("resources", {})
        for sub_name, sub_data in sub_resources.items():
            process_resource(sub_name, sub_data, full_name)

    for r_name, r_data in resources.items():
        process_resource(r_name, r_data)

    with open(target_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved Endpoints Reference: {target_file}")


def main():
    discovery_data = download_discovery()
    download_guides()
    generate_schemas_reference(discovery_data)
    generate_endpoints_reference(discovery_data)
    print("Done downloading official Google Classroom API docs!")


if __name__ == "__main__":
    main()
