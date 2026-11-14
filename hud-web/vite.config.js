import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base: the same dist/ works on GitHub Pages (sub-path) and from the core.
export default defineConfig({ base: "./", plugins: [react()], build: { outDir: "dist", target: "es2020" } });
