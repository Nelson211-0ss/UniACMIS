/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the production image small, which matters when the
  // image has to be copied to a campus server over a slow link.
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        // The service worker must not be cached, or a stale one keeps serving an
        // old app shell after a deploy — on a connection this poor, that could
        // persist for weeks.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
