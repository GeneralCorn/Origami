/**
 * Signing and notarization configuration, read entirely from the
 * environment so that no credential is ever committed.
 *
 *   ORIGAMI_SIGN_IDENTITY               Developer ID Application: ... (TEAMID)
 *   ORIGAMI_APPLE_ID                    Apple ID for notarytool
 *   ORIGAMI_APPLE_APP_SPECIFIC_PASSWORD app-specific password for that Apple ID
 *   ORIGAMI_APPLE_TEAM_ID               10-character team identifier
 *
 * With no identity set the build still succeeds and produces an ad-hoc
 * signed app. Ad-hoc is not a weaker choice, it is the only one available:
 * Apple Silicon refuses to execute a Mach-O with no valid signature, and
 * packaging rewrites Info.plist, which invalidates the signature Electron
 * shipped with. What ad-hoc costs is persistence, because its signature is
 * regenerated on every build and TCC therefore sees a new application each
 * time.
 */

const path = require("node:path");

const BUILD_DIR = path.resolve(__dirname, "..", "build");
const APP_ENTITLEMENTS = path.join(BUILD_DIR, "entitlements.app.plist");
const PYTHON_ENTITLEMENTS = path.join(BUILD_DIR, "entitlements.python.plist");
const ADHOC_ENTITLEMENTS = path.join(BUILD_DIR, "entitlements.adhoc.plist");

const ADHOC_IDENTITY = "-";

const identity = (process.env.ORIGAMI_SIGN_IDENTITY ?? "").trim();
const appleId = (process.env.ORIGAMI_APPLE_ID ?? "").trim();
const applePassword = (process.env.ORIGAMI_APPLE_APP_SPECIFIC_PASSWORD ?? "").trim();
const teamId = (process.env.ORIGAMI_APPLE_TEAM_ID ?? "").trim();

const isAdHoc = identity === "";
const canNotarize = !isAdHoc && appleId !== "" && applePassword !== "" && teamId !== "";

// The sidecar's interpreter, its extension modules, and its dylibs all
// need the sidecar entitlements; the Electron binaries need the app's.
function isPythonBundlePath(filePath) {
  return filePath.includes(`${path.sep}Resources${path.sep}python${path.sep}`);
}

function entitlementsFor(filePath) {
  if (isAdHoc) {
    return ADHOC_ENTITLEMENTS;
  }
  return isPythonBundlePath(filePath) ? PYTHON_ENTITLEMENTS : APP_ENTITLEMENTS;
}

function osxSignOptions() {
  return {
    identity: isAdHoc ? ADHOC_IDENTITY : identity,
    // An ad-hoc identity is not a keychain entry, so there is nothing to
    // look up and the lookup would fail.
    identityValidation: !isAdHoc,
    optionsForFile: (filePath) => ({
      entitlements: entitlementsFor(filePath),
      // Notarization requires it, so every build runs under it. A local
      // build that skipped it would not be exercising the same runtime
      // restrictions the shipped one has to survive.
      hardenedRuntime: true,
    }),
  };
}

function osxNotarizeOptions() {
  if (!canNotarize) {
    return undefined;
  }
  return { appleId, appleIdPassword: applePassword, teamId };
}

function describeSigning() {
  if (isAdHoc) {
    return [
      "signing: ad-hoc (no ORIGAMI_SIGN_IDENTITY set)",
      "  The app will run locally but its signature is regenerated on every",
      "  build, so macOS treats each build as a new application: any Calendar,",
      "  Reminders, Photos, Contacts, or Full Disk Access grant has to be given",
      "  again after every rebuild. Set ORIGAMI_SIGN_IDENTITY to a Developer ID",
      "  Application certificate for grants that persist.",
      "  Entitlements: build/entitlements.adhoc.plist, which carries one key",
      "  the shipped build does not need. See that file for why.",
      "notarization: skipped",
    ].join("\n");
  }
  return [
    `signing: ${identity}`,
    canNotarize
      ? `notarization: enabled for team ${teamId}`
      : "notarization: skipped (set ORIGAMI_APPLE_ID, ORIGAMI_APPLE_APP_SPECIFIC_PASSWORD, and ORIGAMI_APPLE_TEAM_ID to enable)",
  ].join("\n");
}

module.exports = { osxSignOptions, osxNotarizeOptions, describeSigning };
