// Optional: direct read-only access to the shared Postgres for heavy dashboard aggregations.
// The backend API (lib/api.ts) is the primary path — prefer it. Use this only for queries
// that would be expensive to expose as endpoints. The backend owns the schema (Alembic).
import postgres from "postgres";

let _sql: ReturnType<typeof postgres> | null = null;

export function db() {
  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL not set; use the backend API (lib/api.ts) instead.");
  }
  if (!_sql) _sql = postgres(process.env.DATABASE_URL, { max: 4, idle_timeout: 20 });
  return _sql;
}
