import { AdminApiError, parseReport, parseStats, PERIODS, REPORT_FILTERS, type Period, type Report, type ReportFilter, type ReportStatus } from "./contract";

export class AdminApi {
  private readonly fetchImpl: typeof fetch;

  constructor({ fetchImpl = globalThis.fetch }: { fetchImpl?: typeof fetch } = {}) {
    if (typeof fetchImpl !== "function") {
      throw new TypeError("fetchImpl must be a function");
    }
    this.fetchImpl = fetchImpl.bind(globalThis);
  }

  async stats(period: Period) {
    if (!PERIODS.includes(period)) throw new RangeError("unsupported period");
    return parseStats(await this.#readJson(`/api/v1/admin/stats?period=${period}`), period);
  }

  async listReports(filter: ReportFilter): Promise<Report[]> {
    if (!REPORT_FILTERS.includes(filter)) throw new RangeError("unsupported filter");
    const body = await this.#readJson(`/api/v1/admin/reports?status=${filter}`);
    if (typeof body !== "object" || body === null || !("reports" in body) || !Array.isArray(body.reports)) throw new AdminApiError("invalid_response");
    return body.reports.map(parseReport);
  }

  async setReportStatus(reportId: number, status: ReportStatus) {
    const response = await this.#request(`/api/v1/admin/reports/${encodeURIComponent(reportId)}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (response.status === 404) throw new AdminApiError("not_found");
    if (response.status !== 204) throw new AdminApiError("unavailable");
  }

  async #readJson(url: string): Promise<unknown> {
    const response = await this.#request(url, { method: "GET", credentials: "same-origin" });
    if (response.status !== 200) throw new AdminApiError("unavailable");
    try {
      return await response.json();
    } catch {
      throw new AdminApiError("invalid_response");
    }
  }

  async #request(url: string, init: RequestInit) {
    let response;
    try {
      response = await this.fetchImpl(url, init);
    } catch {
      throw new AdminApiError("unavailable");
    }
    if (response.status === 401) throw new AdminApiError("unauthorized");
    if (response.status === 403) throw new AdminApiError("forbidden");
    return response;
  }
}
