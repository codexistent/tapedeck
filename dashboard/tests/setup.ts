import { readFile } from "node:fs/promises";

import { pool } from "@/lib/db";

process.env.DATABASE_URL ??= "postgres://postgres@127.0.0.1:5433/tapedeck_test";

export async function resetDb(): Promise<void> {
  const schema = await readFile(new URL("../db/schema.sql", import.meta.url), "utf8");
  await pool().query("drop schema public cascade; create schema public;");
  await pool().query(schema);
}
