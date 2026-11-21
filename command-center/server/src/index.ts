import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";
import { apiRouter } from "./routes/api.js";
import { healthRouter } from "./routes/health.js";

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const app = express();
const PORT = process.env.PORT || 3001;

// 1. Security & CORS
app.use(cors({
  origin: true,
  credentials: true,
}));

app.use((_req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("X-XSS-Protection", "1; mode=block");
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
  res.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https:;"
  );
  next();
});

// 2. Structured Request Logger
app.use((req, res, next) => {
  const start = Date.now();
  res.on("finish", () => {
    const duration = Date.now() - start;
    if (req.path.startsWith("/api") || req.path === "/health") {
      console.info(JSON.stringify({
        timestamp: new Date().toISOString(),
        method: req.method,
        path: req.path,
        status: res.statusCode,
        durationMs: duration,
        ip: req.ip,
      }));
    }
  });
  next();
});

app.use(express.json());

// 3. Mount API Routes
app.use("/api", apiRouter);
app.use("/", healthRouter);

// 4. Serve Static Production Assets
const clientDistPath = path.resolve(__dirname, "../../../client");
app.use(express.static(clientDistPath));

app.get("*", (req, res, next) => {
  if (req.path.startsWith("/api") || req.path === "/health") {
    return next();
  }
  const indexPath = path.join(clientDistPath, "index.html");
  res.sendFile(indexPath, (err) => {
    if (err) next();
  });
});

// 5. Global Error Handler
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error("[ServerError]", err);
  res.status(500).json({
    ok: false,
    error: err.message || "Internal Server Error",
    timestamp: new Date().toISOString(),
  });
});

// Start listening if executed directly
if (process.env.NODE_ENV !== "test") {
  app.listen(PORT, () => {
    console.info(`[CommandCenter] Server running on http://localhost:${PORT}`);
  });
}
