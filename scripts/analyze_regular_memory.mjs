#!/usr/bin/env node
// Read-only audit of the perf stat campaign. Usage: node scripts/analyze_regular_memory.mjs RESULTS_DIR
import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root || !fs.existsSync(root)) {
  console.error('Usage: node scripts/analyze_regular_memory.mjs RESULTS_DIR');
  process.exit(2);
}
const groups = new Map();
const invalid = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const name = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(name);
    else if (/^perf_[1-5]\.csv$/.test(entry.name)) readPerf(name);
  }
}
function readPerf(file) {
  const rel = path.relative(root, file).split(path.sep);
  if (rel.length !== 6) return;
  const [scope, item, build, threadDir, eventGroup] = rel;
  const key = [scope, item, build, threadDir, eventGroup].join('/');
  const events = {};
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    if (!line || line[0] === '#') continue;
    const fields = line.split(',');
    if (!fields[2] || !['cycles', 'instructions', 'cache-references', 'cache-misses', 'L1-dcache-loads', 'L1-dcache-load-misses', 'LLC-loads', 'LLC-load-misses'].includes(fields[2])) continue;
    const count = Number(fields[0]);
    const coverage = Number(fields[4]);
    events[fields[2]] = { count, coverage };
    if (!Number.isFinite(count) || !Number.isFinite(coverage) || coverage === 0) invalid.push(`${file}: ${line}`);
  }
  const expected = eventGroup === 'basic'
    ? ['cycles', 'instructions', 'cache-references', 'cache-misses']
    : ['L1-dcache-loads', 'L1-dcache-load-misses', 'LLC-loads', 'LLC-load-misses'];
  for (const event of expected) if (!(event in events)) invalid.push(`${file}: missing ${event}`);
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push({ file, events });
}
function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a,b) => a-b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length/2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle-1]+sorted[middle])/2;
}
walk(root);
const summaries = [];
for (const [key, runs] of groups) {
  const [scope, item, build, threads, group] = key.split('/');
  const eventNames = new Set(runs.flatMap(x => Object.keys(x.events)));
  const events = {};
  for (const event of eventNames) {
    const counts = runs.map(x => x.events[event]?.count).filter(Number.isFinite);
    events[event] = {
      count: median(counts),
      min: Math.min(...counts),
      max: Math.max(...counts),
      coverage: median(runs.map(x => x.events[event]?.coverage)),
      minCoverage: Math.min(...runs.map(x => x.events[event]?.coverage).filter(Number.isFinite)),
    };
  }
  const elapsed = [];
  const validations = [];
  if (scope === 'regular') {
    for (const run of runs) {
      const match = path.basename(run.file).match(/perf_(\d+)\.csv/);
      const bench = path.join(path.dirname(run.file), `benchmark_${match[1]}.csv`);
      if (!fs.existsSync(bench)) { invalid.push(`missing ${bench}`); continue; }
      const lines = fs.readFileSync(bench, 'utf8').trim().split(/\r?\n/);
      if (lines.length !== 2) { invalid.push(`unexpected ${bench}: ${lines.length} lines`); continue; }
      const headers = lines[0].split(',');
      const values = lines[1].split(',');
      elapsed.push(Number(values[headers.indexOf('Elapsed_ms')]));
      validations.push(values[headers.indexOf('Validation')]);
    }
  }
  summaries.push({scope, item, build, threads, group, runs: runs.length, events,
    kernelMs: median(elapsed), validation: [...new Set(validations)]});
}
summaries.sort((a,b) => [a.scope,a.item,a.threads,a.build,a.group].join('/').localeCompare([b.scope,b.item,b.threads,b.build,b.group].join('/')));
console.log(JSON.stringify({root, summaries, invalid}, null, 2));
