/* ---------- models & effort (names as in Claude Code) ---------- */
const MODELS = [
  ['', 'Default (recommended)', 'Uses the model your account defaults to'],
  ['claude-fable-5-1', 'Fable 5.1', 'Most capable model'],
  ['claude-opus-5-5', 'Opus 5.5', 'Complex, multi-step work'],
  ['claude-sonnet-5-5', 'Sonnet 5.5', 'Everyday coding and writing'],
  ['claude-haiku-5-5', 'Haiku 5.5', 'Fastest and lightest'],
  ['opusplan', 'Opus Plan Mode', 'Opus plans, Sonnet carries it out'],
];
const EFFORTS = [['', 'Auto'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High'], ['xhigh', 'Extra high'], ['max', 'Max']];
function modelName(id) {
  if (!id) return '';
  const k = MODELS.find(m => m[0] === id); if (k) return k[1];
  const m = id.match(/^claude-([a-z]+)-(\d+)-(\d+)/); if (m) return m[1][0].toUpperCase() + m[1].slice(1) + ' ' + m[2] + '.' + m[3];
  return id;
}
const effortName = e => (EFFORTS.find(x => x[0] === e) || ['', ''])[1];
const MODES = [['acceptEdits', 'Accept edits', 'Edits files freely; other actions need a rule'], ['default', 'Default', 'Reads only; other actions need a permission rule'], ['plan', 'Plan mode', 'Claude plans and makes no changes'], ['bypassPermissions', 'Bypass permissions', 'Runs everything without asking']];
const modeName = v => (MODES.find(m => m[0] === v) || MODES[0])[1];

