import { build, type InlineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fg from "fast-glob";
import path from "path";
import fs from "fs";
import tailwindcss from "@tailwindcss/vite";

const outDir = "assets";

const GLOBAL_CSS = [path.resolve("src/index.css")];

function wrapEntryPlugin(
  virtualId: string,
  entryFile: string,
  cssPaths: string[]
): Plugin {
  return {
    name: `virtual-entry-wrapper:${entryFile}`,
    resolveId(id) {
      if (id === virtualId) return id;
    },
    load(id) {
      if (id !== virtualId) return null;
      const cssImports = cssPaths
        .map((css) => `import ${JSON.stringify(css)};`)
        .join("\n");
      return `
        ${cssImports}
        export * from ${JSON.stringify(entryFile)};
        import * as __entry from ${JSON.stringify(entryFile)};
        export default (__entry.default ?? __entry.App);
        import ${JSON.stringify(entryFile)};
      `;
    },
  };
}

fs.rmSync(outDir, { recursive: true, force: true });

const entries = fg.sync("src/**/index.{tsx,jsx}");

for (const file of entries) {
  const name = path.basename(path.dirname(file));
  const entryAbs = path.resolve(file);
  const entryDir = path.dirname(entryAbs);

  const perEntryCss = fg.sync("**/*.css", {
    cwd: entryDir,
    absolute: true,
    dot: false,
    ignore: ["**/*.module.*"],
  });

  const globalCss = GLOBAL_CSS.filter((p) => fs.existsSync(p));
  const cssToInclude = [...globalCss, ...perEntryCss].filter((p) => fs.existsSync(p));

  const virtualId = `\0virtual-entry:${entryAbs}`;

  const config: InlineConfig = {
    plugins: [
      wrapEntryPlugin(virtualId, entryAbs, cssToInclude),
      tailwindcss(),
      react(),
    ],
    esbuild: {
      jsx: "automatic",
      jsxImportSource: "react",
      target: "es2022",
    },
    build: {
      target: "es2022",
      outDir,
      emptyOutDir: false,
      chunkSizeWarningLimit: 2000,
      minify: "esbuild",
      cssCodeSplit: false,
      rollupOptions: {
        input: virtualId,
        output: {
          format: "es",
          entryFileNames: `${name}.js`,
          inlineDynamicImports: true,
          assetFileNames: (info) =>
            (info.name || "").endsWith(".css")
              ? `${name}.css`
              : `[name]-[hash][extname]`,
        },
        preserveEntrySignatures: "allow-extension",
        treeshake: true,
      },
    },
  };

  console.log(`Building ${name}...`);
  await build(config);
  console.log(`Built ${name}`);

  // Inline CSS and JS into a single HTML file
  const cssPath = path.join(outDir, `${name}.css`);
  const jsPath = path.join(outDir, `${name}.js`);
  const cssContent = fs.existsSync(cssPath) ? fs.readFileSync(cssPath, "utf8") : "";
  const jsContent = fs.readFileSync(jsPath, "utf8");

  const html = `<!doctype html>
<html>
<head>
  <style>${cssContent}</style>
</head>
<body>
  <div id="${name}-root"></div>
  <script type="module">${jsContent}</script>
</body>
</html>
`;
  fs.writeFileSync(path.join(outDir, `${name}.html`), html, "utf8");
  console.log(`Generated ${name}.html`);
}
