import { ZodSchema } from "zod";

interface CacheEntry<T> {
  data: T;
  cachedAt: number;
  expiresAt: number;
  lastGoodAt: number;
}

interface CircuitBreakerState {
  failureCount: number;
  lastFailureTime: number;
  isOpen: boolean;
}

export class ResilientCache {
  private cache = new Map<string, CacheEntry<any>>();
  private inFlightPromises = new Map<string, Promise<any>>();
  private circuitBreakers = new Map<string, CircuitBreakerState>();

  private readonly failureThreshold = 3;
  private readonly cooldownPeriodMs = 30000; // 30s cooldown before retrying an open circuit

  /**
   * Fetch with cache, request deduplication, circuit breaker, and stale-fallback on upstream error
   */
  async getOrFetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    ttlSeconds: number,
    schema?: ZodSchema<T>
  ): Promise<{ data: T; isStale: boolean; lastGoodAt: string; fromCache: boolean }> {
    const now = Date.now();
    const entry = this.cache.get(key);

    // 1. Fresh cache hit
    if (entry && entry.expiresAt > now) {
      return {
        data: entry.data,
        isStale: false,
        lastGoodAt: new Date(entry.lastGoodAt).toISOString(),
        fromCache: true,
      };
    }

    // 2. Circuit breaker check
    const cb = this.getCircuitBreaker(key);
    if (cb.isOpen) {
      if (now - cb.lastFailureTime < this.cooldownPeriodMs) {
        // Circuit open and in cooldown: serve stale if available
        if (entry) {
          console.warn(`[Cache] Circuit open for ${key}; serving stale data from ${new Date(entry.lastGoodAt).toISOString()}`);
          return {
            data: entry.data,
            isStale: true,
            lastGoodAt: new Date(entry.lastGoodAt).toISOString(),
            fromCache: true,
          };
        }
        throw new Error(`Circuit breaker open for upstream service: ${key}`);
      } else {
        // Cooldown passed, attempt half-open probe
        console.info(`[Cache] Circuit half-open probe for ${key}`);
        cb.isOpen = false;
      }
    }

    // 3. Request deduplication (single flight)
    if (this.inFlightPromises.has(key)) {
      try {
        const result = await this.inFlightPromises.get(key);
        return {
          data: result,
          isStale: false,
          lastGoodAt: new Date(this.cache.get(key)?.lastGoodAt || now).toISOString(),
          fromCache: true,
        };
      } catch (err) {
        // If the shared promise failed, handle fallback below
      }
    }

    // 4. Execute fetcher
    const fetchPromise: Promise<T> = (async (): Promise<T> => {
      try {
        console.info(`[Cache] Fetching fresh data for ${key}`);
        const rawData = await fetcher();

        let validatedData: T = rawData;
        if (schema) {
          const parsed = schema.safeParse(rawData);
          if (!parsed.success) {
            console.error(`[Validation] Schema failure for ${key}:`, parsed.error.issues);
            throw new Error(`Schema validation failed for ${key}: ${parsed.error.message}`);
          }
          validatedData = parsed.data as T;
        }

        // Success: reset circuit breaker
        this.resetCircuitBreaker(key);

        const newEntry: CacheEntry<T> = {
          data: validatedData,
          cachedAt: now,
          expiresAt: now + ttlSeconds * 1000,
          lastGoodAt: now,
        };
        this.cache.set(key, newEntry);

        return validatedData;
      } catch (err: any) {
        console.error(`[Cache] Error fetching upstream for ${key}:`, err.message);
        this.recordFailure(key);
        throw err;
      } finally {
        this.inFlightPromises.delete(key);
      }
    })();

    this.inFlightPromises.set(key, fetchPromise);

    try {
      const fetchedData = await fetchPromise;
      const currentEntry = this.cache.get(key);
      const isStale = currentEntry ? currentEntry.expiresAt <= now : false;

      return {
        data: fetchedData,
        isStale,
        lastGoodAt: new Date(currentEntry?.lastGoodAt || now).toISOString(),
        fromCache: false,
      };
    } catch (error) {
      if (entry) {
        return {
          data: entry.data,
          isStale: true,
          lastGoodAt: new Date(entry.lastGoodAt).toISOString(),
          fromCache: true,
        };
      }
      throw error;
    }
  }

  /**
   * Set cache entry directly (useful for tests or mock mode)
   */
  set<T>(key: string, data: T, ttlSeconds: number): void {
    const now = Date.now();
    this.cache.set(key, {
      data,
      cachedAt: now,
      expiresAt: now + ttlSeconds * 1000,
      lastGoodAt: now,
    });
  }

  /**
   * Invalidate a key
   */
  invalidate(key: string): void {
    this.cache.delete(key);
  }

  /**
   * Get health report of cached entries
   */
  getHealthReport(): Record<string, { cached: boolean; isStale: boolean; lastGoodAt?: string; circuitOpen: boolean }> {
    const now = Date.now();
    const report: Record<string, any> = {};

    for (const [key, entry] of this.cache.entries()) {
      const cb = this.getCircuitBreaker(key);
      report[key] = {
        cached: true,
        isStale: entry.expiresAt <= now,
        lastGoodAt: new Date(entry.lastGoodAt).toISOString(),
        circuitOpen: cb.isOpen,
      };
    }

    return report;
  }

  private getCircuitBreaker(key: string): CircuitBreakerState {
    if (!this.circuitBreakers.has(key)) {
      this.circuitBreakers.set(key, { failureCount: 0, lastFailureTime: 0, isOpen: false });
    }
    return this.circuitBreakers.get(key)!;
  }

  private recordFailure(key: string): void {
    const cb = this.getCircuitBreaker(key);
    cb.failureCount++;
    cb.lastFailureTime = Date.now();
    if (cb.failureCount >= this.failureThreshold) {
      cb.isOpen = true;
      console.warn(`[Cache] Circuit breaker TRIPPED for ${key} after ${cb.failureCount} failures`);
    }
  }

  private resetCircuitBreaker(key: string): void {
    const cb = this.getCircuitBreaker(key);
    cb.failureCount = 0;
    cb.isOpen = false;
  }
}

export const globalCache = new ResilientCache();
