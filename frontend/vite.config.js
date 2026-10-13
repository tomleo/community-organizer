import { resolve } from "node:path";
import { defineConfig } from "vite";

// Output plain, unhashed files; Django's ManifestStaticFilesStorage adds hashes at collectstatic.
export default defineConfig({
  build: {
    outDir: resolve(import.meta.dirname, "../static/dist"),
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        main: resolve(import.meta.dirname, "src/main.js"),
        manage: resolve(import.meta.dirname, "src/manage.js"),
      },
      output: {
        entryFileNames: "[name].js",
        assetFileNames: "[name][extname]",
      },
    },
  },
  css: {
    preprocessorOptions: {
      scss: { quietDeps: true, silenceDeprecations: ["import"] },
    },
  },
});
