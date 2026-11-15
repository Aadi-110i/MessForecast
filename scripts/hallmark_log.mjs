/**
 * Write the Hallmark build entry into .hallmark/log.json.
 *
 * The entry is read from a file and passed as a single argument so that no
 * shell quoting can mangle it.
 *
 * Usage: node scripts/hallmark_log.mjs [.hallmark/entry.json]
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const entryPath = resolve(ROOT, process.argv[2] || '.hallmark/entry.json');
const entry = readFileSync(entryPath, 'utf8').trim();

const themeScript = join(
  process.env.HALLMARK_HOME || 'C:/Users/Dell/.agents/skills/hallmark',
  'scripts/theme.mjs'
);

const result = spawnSync(
  process.execPath,
  [themeScript, 'log', '--entry', entry, '--log', join(ROOT, '.hallmark/log.json')],
  { cwd: ROOT, encoding: 'utf8' }
);

process.stdout.write(result.stdout || '');
process.stderr.write(result.stderr || '');
process.exit(result.status ?? 0);
