import { describe, it, expect } from "vitest";
import {
  formatINR,
  formatUSD,
  formatPrice,
  formatPercentChange,
  formatToIST,
  formatRelativeTime,
} from "../shared/formatters.js";

describe("Shared Formatters", () => {
  describe("formatINR", () => {
    it("formats standard INR values with Indian comma grouping", () => {
      expect(formatINR(1000)).toBe("₹1,000.00");
      expect(formatINR(123456.78)).toBe("₹1,23,456.78");
      expect(formatINR(10000000)).toBe("₹1,00,00,000.00");
    });

    it("formats compact INR with Lakh and Crore", () => {
      expect(formatINR(250000, { compact: true })).toBe("₹2.50 L");
      expect(formatINR(15000000, { compact: true })).toBe("₹1.50 Cr");
      expect(formatINR(-35000000, { compact: true })).toBe("-₹3.50 Cr");
    });

    it("handles zero and negative amounts", () => {
      expect(formatINR(0)).toBe("₹0.00");
      expect(formatINR(-5000)).toBe("-₹5,000.00");
    });
  });

  describe("formatUSD", () => {
    it("formats USD with standard international grouping", () => {
      expect(formatUSD(1234567.89)).toBe("$1,234,567.89");
      expect(formatUSD(1000)).toBe("$1,000.00");
    });

    it("formats compact USD values", () => {
      expect(formatUSD(2500000, { compact: true })).toBe("$2.50M");
      expect(formatUSD(1200000000, { compact: true })).toBe("$1.20B");
      expect(formatUSD(4500, { compact: true })).toBe("$4.5k");
    });
  });

  describe("formatPrice", () => {
    it("routes by currency correctly", () => {
      expect(formatPrice(50000, "INR")).toBe("₹50,000.00");
      expect(formatPrice(50000, "USD")).toBe("$50,000.00");
    });
  });

  describe("formatPercentChange", () => {
    it("formats positive changes with + sign and up arrow", () => {
      const res = formatPercentChange(2.45);
      expect(res.sign).toBe("+");
      expect(res.arrow).toBe("▲");
      expect(res.direction).toBe("up");
      expect(res.text).toBe("+2.45%");
    });

    it("formats negative changes with - sign and down arrow", () => {
      const res = formatPercentChange(-3.12);
      expect(res.sign).toBe("-");
      expect(res.arrow).toBe("▼");
      expect(res.direction).toBe("down");
      expect(res.text).toBe("-3.12%");
    });

    it("formats flat 0% change", () => {
      const res = formatPercentChange(0);
      expect(res.sign).toBe("");
      expect(res.arrow).toBe("▬");
      expect(res.direction).toBe("flat");
      expect(res.text).toBe("0.00%");
    });
  });

  describe("formatToIST", () => {
    it("correctly converts UTC to Asia/Kolkata (IST = UTC+05:30)", () => {
      // 2026-11-21T04:00:00Z -> +5h30m = 09:30 AM IST on Nov 21
      const res = formatToIST("2026-11-21T04:00:00Z");
      expect(res).toContain("IST");
      expect(res).toMatch(/09:30\s*(am|AM|pm|PM)?/i);
    });

    it("handles date boundary crossing from UTC night to next morning IST", () => {
      // 2026-11-21T20:00:00Z -> +5h30m = 01:30 AM IST on Nov 22
      const res = formatToIST("2026-11-21T20:00:00Z");
      expect(res).toContain("22");
      expect(res).toContain("IST");
    });
  });

  describe("formatRelativeTime", () => {
    const fixedNow = new Date("2026-11-21T12:00:00Z");

    it("formats minutes and hours ago", () => {
      const tenMinsAgo = new Date("2026-11-21T11:50:00Z");
      expect(formatRelativeTime(tenMinsAgo, fixedNow)).toBe("10m ago");

      const threeHoursAgo = new Date("2026-11-21T09:00:00Z");
      expect(formatRelativeTime(threeHoursAgo, fixedNow)).toBe("3h ago");
    });

    it("formats future countdowns", () => {
      const futureIn30Mins = new Date("2026-11-21T12:30:00Z");
      expect(formatRelativeTime(futureIn30Mins, fixedNow)).toBe("in 30m");
    });
  });
});
