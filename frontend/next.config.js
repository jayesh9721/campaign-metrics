/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output is required by frontend/Dockerfile (copies .next/standalone).
  output: "standalone",
};

module.exports = nextConfig;
