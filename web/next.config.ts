import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Fully static: the JSON is read at build time, nothing runs at request time.
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
