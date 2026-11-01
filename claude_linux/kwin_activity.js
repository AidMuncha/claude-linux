// Loaded into KWin (Plasma 6) by claude_linux/activity.py.
// 1. Reports which window you are in, tab/title changes, and windows opening or closing.
// 2. Places Jarvis' own windows: "Jarvis HUD" (the orb, bottom-left above the panel) and "Jarvis Screen" (a see-through overlay over the whole monitor the
//    pointer is on, where the reading highlight is drawn). Both stay on top, off the taskbar and without a frame.
const SVC = "dev.nein.ClaudeLinux.Jarvis", PATH = "/jarvis", HUD = "Jarvis HUD", SCREEN = "Jarvis Screen";
let prev = null;
function isHud(w) { return !!w && String(w.caption).indexOf(HUD) === 0; }
function isScreen(w) { return !!w && String(w.caption) === SCREEN; }
function ours(w) { return isHud(w) || isScreen(w); }
function boring(w) { return !w || ours(w) || w.specialWindow || w.desktopWindow || w.dock || w.notification || w.criticalNotification || w.onScreenDisplay || w.popupWindow || w.tooltip || w.appletPopup; }
function send(kind, w) {
  callDBus(SVC, PATH, SVC, "Event", kind, String(w.internalId), String(w.resourceClass || ""), String(w.caption || ""));
}
function set(w, prop, value) { try { w[prop] = value; } catch (e) {} }
function place(w) {
  const g = w.frameGeometry;
  if (g.width < 50) return;
  let r;
  if (isScreen(w)) {
    let out = null;
    try { out = workspace.screenAt(workspace.cursorPos); } catch (e) {}
    const a = out ? out.geometry : workspace.virtualScreenGeometry;
    r = { x: a.x, y: a.y, width: a.width, height: a.height };
  } else {
    let a;
    try { a = workspace.clientArea(KWin.MaximizedArea, w); } catch (e) { a = workspace.virtualScreenGeometry; }
    r = { x: a.x, y: a.y + a.height - g.height, width: g.width, height: g.height };
  }
  if (Math.round(g.x) !== r.x || Math.round(g.y) !== r.y || Math.round(g.width) !== r.width || Math.round(g.height) !== r.height) w.frameGeometry = r;
}
const placed = {};
function adopt(w) {
  if (!ours(w)) return false;
  const id = String(w.internalId);
  if (!placed[id]) {
    placed[id] = true;
    set(w, "keepAbove", true); set(w, "skipTaskbar", true); set(w, "skipPager", true); set(w, "skipSwitcher", true); set(w, "noBorder", true); set(w, "onAllDesktops", true);
    w.frameGeometryChanged.connect(function () { place(w); });
    // neither needs the keyboard (except the text-mode HUD), so give focus straight back to whatever you were using
    if (String(w.caption) !== HUD + " text" && prev) workspace.activeWindow = prev;
  }
  place(w);
  return true;
}
function track(w) {
  if (adopt(w)) return;
  if (boring(w)) return;
  w.captionChanged.connect(function () { if (adopt(w)) return; if (workspace.activeWindow === w) send("title", w); });
}
workspace.windowActivated.connect(function (w) {
  if (adopt(w)) return;
  if (!boring(w)) { prev = w; send("active", w); }
  // a fullscreen game sits in a layer above "keep above": step it out of fullscreen so the orb stays visible
  try { if (w && !boring(w) && w.fullScreen) w.fullScreen = false; } catch (e) {}
  workspace.windowList().forEach(function (o) { if (ours(o)) { try { workspace.raiseWindow(o); } catch (e) {} } });
});
workspace.windowAdded.connect(function (w) {
  track(w);
  if (!ours(w) && !boring(w)) send("opened", w);
});
workspace.windowRemoved.connect(function (w) { if (w === prev) prev = null; if (!boring(w)) send("closed", w); });
workspace.windowList().forEach(function (w) { track(w); if (!boring(w)) send("existing", w); });
if (workspace.activeWindow && !boring(workspace.activeWindow)) { prev = workspace.activeWindow; send("active", workspace.activeWindow); }
