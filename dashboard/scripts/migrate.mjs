// Applies db/schema.sql. Runs before every build; skipped when DATABASE_URL is unset
// (e.g. a local build with no database), so builds never fail for lack of one.
import { readFile } from "node:fs/promises";
import pg from "pg";

const url = process.env.DATABASE_URL;
if (!url) {
  console.log("migrate: DATABASE_URL not set, skipping");
  process.exit(0);
}

const sql = await readFile(new URL("../db/schema.sql", import.meta.url), "utf8");
const client = new pg.Client({
  connectionString: url,
  ssl: /localhost|127\.0\.0\.1/.test(url) ? false : { rejectUnauthorized: true },
});
await client.connect();
try {
  await client.query(sql);
  console.log("migrate: schema up to date");
} finally {
  await client.end();
}
