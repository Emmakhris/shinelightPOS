// Starts Django on a throwaway SQLite database for the end-to-end tests.
// Django serves the built frontend (npm run build), exactly as in a shop install.
import { spawn, spawnSync } from 'node:child_process'
import { rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const backend = path.resolve(here, '../../backend')
const python = process.platform === 'win32'
  ? path.join(backend, '.venv', 'Scripts', 'python.exe')
  : path.join(backend, '.venv', 'bin', 'python')
const db = path.join(backend, 'e2e.sqlite3')
const port = process.env.E2E_PORT ?? '8001'

const backups = path.join(backend, 'e2e-backups')
rmSync(db, { force: true })
rmSync(backups, { recursive: true, force: true })
// sk_fake runs the built-in Paystack simulator: MoMo prompts work offline and move no money.
const env = {
  ...process.env,
  DATABASE_URL: `sqlite:///${db.replace(/\\/g, '/')}`,
  DEBUG: 'true',
  PAYSTACK_SECRET_KEY: 'sk_fake',
  BACKUP_DIR: backups,
}

const migrate = spawnSync(python, ['manage.py', 'migrate', '-v', '0'], { cwd: backend, env, stdio: 'inherit' })
if (migrate.status !== 0) process.exit(migrate.status ?? 1)

const server = spawn(python, ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload'], { cwd: backend, env, stdio: 'inherit' })
const stop = () => server.kill()
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
process.on('exit', stop)
server.on('exit', (code) => process.exit(code ?? 0))
