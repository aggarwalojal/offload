import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  experimental: { agentFeedback: true },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
