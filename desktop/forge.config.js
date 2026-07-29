const { execFileSync } = require("node:child_process");
const path = require("node:path");

const { osxSignOptions, osxNotarizeOptions, describeSigning } = require("./scripts/signing");

const ROOT = __dirname;

// TCC binds a permission grant to the code signature, the bundle
// identifier, and the on-disk path. Changing this string makes every
// grant a user has already given start over, so it is frozen.
const BUNDLE_ID = "com.generalcorn.origami";

// Declared ahead of the connectors that need them. macOS attributes the
// sidecar's requests to this bundle and checks these keys; when one is
// missing, access is denied with no prompt and no error, and an empty
// result is indistinguishable from an empty calendar. See
// docs/INTEGRATIONS_RESEARCH.md section 4.
const USAGE_DESCRIPTIONS = {
  NSCalendarsUsageDescription:
    "Origami indexes your events so you can search them and ask questions about them alongside your notes. The index is stored on this Mac.",
  NSRemindersUsageDescription:
    "Origami indexes your reminders so your tasks show up when you search or ask about what you have to do. The index is stored on this Mac.",
  NSPhotoLibraryUsageDescription:
    "Origami indexes the photos you choose so you can find them by what they show rather than by filename. The index is stored on this Mac.",
  NSContactsUsageDescription:
    "Origami reads your contacts so messages and events show the names of the people involved instead of phone numbers and email addresses. The index is stored on this Mac.",
};

function run(command, args, env) {
  execFileSync(command, args, { cwd: ROOT, stdio: "inherit", env: { ...process.env, ...env } });
}

module.exports = {
  packagerConfig: {
    name: "Origami",
    executableName: "Origami",
    appBundleId: BUNDLE_ID,
    appCategoryType: "public.app-category.productivity",
    asar: true,
    // The renderer is a Vite bundle and the main process is compiled to
    // dist/, so nothing under node_modules is reachable at runtime.
    ignore: (filePath) => filePath !== "" && filePath !== "/package.json" && filePath !== "/dist" && !filePath.startsWith("/dist/"),
    extraResource: [
      path.join(ROOT, "resources", "python"),
      path.join(ROOT, "resources", "backend"),
    ],
    extendInfo: USAGE_DESCRIPTIONS,
    osxSign: osxSignOptions(),
    osxNotarize: osxNotarizeOptions(),
  },
  makers: [
    {
      name: "@electron-forge/maker-zip",
      platforms: ["darwin"],
    },
    {
      name: "@electron-forge/maker-dmg",
      platforms: ["darwin"],
      config: {
        // lzfse, which is worth having on a bundle this size
        format: "ULFO",
        overwrite: true,
      },
    },
  ],
  hooks: {
    generateAssets: async (_forgeConfig, _platform, arch) => {
      process.stdout.write(`${describeSigning()}\n`);
      run("npm", ["run", "build:main"]);
      run("npm", ["run", "build:renderer"]);
      // The interpreter is architecture-specific, so a cross-build has to
      // fetch the matching one rather than the host's.
      run("node", ["scripts/bundle-python.mjs"], arch ? { ORIGAMI_TARGET_ARCH: arch } : undefined);
    },
  },
};
