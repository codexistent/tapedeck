import pg from "pg";

declare global {
  // Reused across hot reloads in dev and across invocations of a warm serverless instance.
  var __tapedeckPool: pg.Pool | undefined;
}

function makePool(): pg.Pool {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  const local = /localhost|127\.0\.0\.1/.test(url);
  return new pg.Pool({
    connectionString: url,
    ssl: local ? false : { rejectUnauthorized: true },
    max: 5,
  });
}

export function pool(): pg.Pool {
  globalThis.__tapedeckPool ??= makePool();
  return globalThis.__tapedeckPool;
}

export async function query<T extends pg.QueryResultRow>(
  text: string,
  params: unknown[] = [],
): Promise<T[]> {
  const result = await pool().query<T>(text, params);
  return result.rows;
}

export async function one<T extends pg.QueryResultRow>(
  text: string,
  params: unknown[] = [],
): Promise<T | null> {
  const rows = await query<T>(text, params);
  return rows[0] ?? null;
}

/** Run ``fn`` inside a transaction; rolls back on any error. */
export async function tx<R>(fn: (client: pg.PoolClient) => Promise<R>): Promise<R> {
  const client = await pool().connect();
  try {
    await client.query("begin");
    const result = await fn(client);
    await client.query("commit");
    return result;
  } catch (error) {
    await client.query("rollback");
    throw error;
  } finally {
    client.release();
  }
}
