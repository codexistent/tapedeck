import { createHash, randomBytes } from "node:crypto";

const PREFIX = "tdk_";

/** A new API token. The plaintext is returned once; only its hash is stored. */
export function newToken(): { token: string; prefix: string; hash: string } {
  const token = PREFIX + randomBytes(24).toString("base64url");
  return { token, prefix: token.slice(0, PREFIX.length + 6), hash: hashToken(token) };
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

/** Extract a bearer token from an Authorization header, or null. */
export function bearer(header: string | null): string | null {
  if (!header) return null;
  const match = /^Bearer\s+(\S+)$/i.exec(header.trim());
  if (!match) return null;
  return match[1].startsWith(PREFIX) ? match[1] : null;
}

const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/;

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
}

export function isSlug(value: string): boolean {
  return SLUG.test(value);
}
