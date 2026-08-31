/*
 * Script IDE launch tile - redirect stub.
 *
 * Served at /res/scriptide/launcher.js and mounted as the Gateway home-page
 * "Script IDE" nav tile (see ScriptIdeModuleHook#setup and
 * ModuleConstants.LAUNCHER_BUNDLE_NAME). The Gateway shell script-loads this
 * file, reads the UMD global window.ScriptIdeLauncher, and renders its
 * `ScriptIdeLauncher` export as a React function component. That component
 * immediately redirects the whole browser to the standalone full-page SPA, then
 * renders nothing.
 *
 * Hand-written rather than bundled, on purpose. It needs no React import (it
 * returns null), and keeping it out of the Vite bundle means the one file the
 * Gateway shell loads through SystemJS stays dependency-free - which matters,
 * because React 19 dropped UMD builds and the shell's loader needs a UMD global.
 * The wrapper mirrors the shape webpack's `libraryTarget: "umd"` emits, so the
 * loader resolves it as window[moduleName][exportName].
 *
 * The redirect target is duplicated from ScriptIdePaths.SPA_LAUNCH_TARGET - a
 * static asset cannot import a Java constant. Keep the two in sync. The trailing
 * slash is load-bearing: /data/scriptide (no slash) returns 404.
 */
(function (root, factory) {
  if (typeof exports === "object" && typeof module === "object") {
    module.exports = factory();
  } else if (typeof define === "function" && define.amd) {
    define("ScriptIdeLauncher", [], factory);
  } else if (typeof exports === "object") {
    exports.ScriptIdeLauncher = factory();
  } else {
    root.ScriptIdeLauncher = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Keep in sync with ScriptIdePaths.SPA_LAUNCH_TARGET.
  var TARGET = "/data/scriptide/";

  // Renders nothing; navigates the browser out of the Gateway shell to the full
  // page. location.replace keeps the stub out of history, so Back returns to the
  // Gateway home page instead of bouncing through the redirect again.
  function ScriptIdeLauncher() {
    try {
      var win = (window.top && window.top !== window.self) ? window.top : window;
      win.location.replace(TARGET);
    } catch (e) {
      // Cross-origin framing guard - fall back to this window.
      window.location.replace(TARGET);
    }
    return null;
  }

  return {
    ScriptIdeLauncher: ScriptIdeLauncher,
    default: ScriptIdeLauncher
  };
});
