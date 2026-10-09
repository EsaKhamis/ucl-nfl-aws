import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Pin the file-tracing root to this app so Next does not infer a parent
  // directory (a stray lockfile in the home dir was being picked up).
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
