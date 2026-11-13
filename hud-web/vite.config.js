import { defineConfig } from "vite";

// Relative base: the same dist/ works on GitHub Pages (sub-path) and from the core.
export default defineConfig({ base: "./", build: { outDir: "dist", target: "es2020" } });
