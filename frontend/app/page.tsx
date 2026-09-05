"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const API_BASE = "http://localhost:8000/api/metrics";
const API_KEY = process.env.NEXT_PUBLIC_METRICS_API_KEY || "";

if (!API_KEY) {
  console.error("FATAL: NEXT_PUBLIC_METRICS_API_KEY environment variable not set");
  console.error("Set it in .env.local file");
}

export default function Dashboard() {
  const [funnelData, setFunnelData] = useState<any>(null);
  const [categoryData, setCategoryData] = useState<any>(null);
  const [falsePositiveRate, setFalsePositiveRate] = useState<any>(null);
  const [latency, setLatency] = useState<any>(null);
  const [guardrailHits, setGuardrailHits] = useState<any>(null);
  const [auditTrail, setAuditTrail] = useState<any>(null);
  const [hinglishExamples, setHinglishExamples] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [selectedEntry, setSelectedEntry] = useState<any>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = {
        'X-API-Key': API_KEY,
      };

      const [funnel, category, falsePos, lat, guardrail, audit, hinglish, statsData] =
        await Promise.all([
          fetch(`${API_BASE}/funnel`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch funnel: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/recovery-by-category`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch category: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/false-positive-rate`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch false-positive: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/latency`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch latency: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/guardrail-hits`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch guardrails: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/audit-trail?limit=20`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch audit trail: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/hinglish-examples`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch hinglish: ${r.status}`);
            return r.json();
          }),
          fetch(`${API_BASE}/stats`, { headers }).then((r) => {
            if (!r.ok) throw new Error(`Failed to fetch stats: ${r.status}`);
            return r.json();
          }),
        ]);

      setFunnelData(funnel);
      setCategoryData(category);
      setFalsePositiveRate(falsePos);
      setLatency(lat);
      setGuardrailHits(guardrail);
      setAuditTrail(audit);
      setHinglishExamples(hinglish);
      setStats(statsData);
    } catch (error) {
      console.error("Failed to fetch data:", error);
      setError(error instanceof Error ? error.message : "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  const formatCurrency = (paise: number) => {
    return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
  };

  const formatLatency = (seconds: number) => {
    if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} hrs`;
    return `${(seconds / 86400).toFixed(1)} days`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
          <div className="flex items-center justify-center w-12 h-12 bg-red-100 rounded-full mx-auto mb-4">
            <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 text-center mb-2">
            Backend Unreachable
          </h3>
          <p className="text-sm text-gray-600 text-center mb-6">
            {error}
          </p>
          <div className="space-y-3">
            <button
              onClick={fetchAllData}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Retry Connection
            </button>
            <div className="text-xs text-gray-500 text-center">
              <p>Make sure the backend is running at:</p>
              <code className="bg-gray-100 px-2 py-1 rounded mt-1 inline-block">
                {API_BASE}
              </code>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">
            AI Revenue Recovery Agent
          </h1>
          <p className="text-gray-600 mt-1">
            Razorpay Buildathon · Track 03 · Real-time Dashboard
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            <button
              onClick={() => setActiveTab("overview")}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === "overview"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveTab("hinglish")}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === "hinglish"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Hinglish Messages
            </button>
            <button
              onClick={() => setActiveTab("audit")}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === "audit"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              Audit Trail
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Overview Tab */}
        {activeTab === "overview" && stats && (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <div className="bg-white p-6 rounded-lg shadow">
                <p className="text-sm text-gray-600">Total Actions</p>
                <p className="text-3xl font-bold text-gray-900 mt-2">
                  {stats.total_recovery_actions}
                </p>
              </div>
              <div className="bg-white p-6 rounded-lg shadow">
                <p className="text-sm text-gray-600">Executed</p>
                <p className="text-3xl font-bold text-green-600 mt-2">
                  {stats.executed_actions}
                </p>
              </div>
              <div className="bg-white p-6 rounded-lg shadow">
                <p className="text-sm text-gray-600">Blocked</p>
                <p className="text-3xl font-bold text-orange-600 mt-2">
                  {stats.blocked_actions}
                </p>
              </div>
              <div className="bg-white p-6 rounded-lg shadow">
                <p className="text-sm text-gray-600">Failed Transactions</p>
                <p className="text-3xl font-bold text-red-600 mt-2">
                  {stats.source_records.failed_transactions}
                </p>
              </div>
            </div>

            {/* Funnel View */}
            {funnelData && (
              <div className="bg-white p-6 rounded-lg shadow">
                <h2 className="text-xl font-bold text-gray-900 mb-4">
                  Revenue Recovery Funnel
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="text-center p-4 bg-blue-50 rounded-lg">
                    <p className="text-sm text-gray-600">At-Risk Revenue</p>
                    <p className="text-2xl font-bold text-blue-600 mt-2">
                      {formatCurrency(funnelData.total_at_risk_paise)}
                    </p>
                  </div>
                  <div className="text-center p-4 bg-green-50 rounded-lg">
                    <p className="text-sm text-gray-600">Actions Taken</p>
                    <p className="text-2xl font-bold text-green-600 mt-2">
                      {funnelData.actions_taken}
                    </p>
                  </div>
                  <div className="text-center p-4 bg-emerald-50 rounded-lg">
                    <p className="text-sm text-gray-600">Recovered (Est.)</p>
                    <p className="text-2xl font-bold text-emerald-600 mt-2">
                      {formatCurrency(funnelData.amount_recovered_paise)}
                    </p>
                    <p className="text-sm text-gray-500 mt-1">
                      {funnelData.recovery_rate_percentage}% recovery rate
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Recovery by Category */}
            {categoryData && categoryData.categories.length > 0 && (
              <div className="bg-white p-6 rounded-lg shadow">
                <h2 className="text-xl font-bold text-gray-900 mb-4">
                  Recovery by Category
                </h2>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={categoryData.categories}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="category" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="executed" fill="#10b981" name="Executed" />
                    <Bar dataKey="blocked" fill="#f59e0b" name="Blocked" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* False Positive & Latency */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {falsePositiveRate && (
                <div className="bg-white p-6 rounded-lg shadow">
                  <h2 className="text-xl font-bold text-gray-900 mb-4">
                    False Positive Rate
                  </h2>
                  <div className="text-center">
                    <p className="text-4xl font-bold text-orange-600">
                      {falsePositiveRate.false_positive_rate_percentage}%
                    </p>
                    <p className="text-sm text-gray-600 mt-2">
                      {falsePositiveRate.estimated_no_response} of{" "}
                      {falsePositiveRate.total_actions_executed} actions got no response
                    </p>
                    <p className="text-xs text-gray-500 mt-4">
                      {falsePositiveRate.note}
                    </p>
                  </div>
                </div>
              )}

              {latency && (
                <div className="bg-white p-6 rounded-lg shadow">
                  <h2 className="text-xl font-bold text-gray-900 mb-4">
                    Response Latency
                  </h2>
                  <div className="text-center">
                    <p className="text-4xl font-bold text-blue-600">
                      {formatLatency(latency.average_latency_seconds)}
                    </p>
                    <p className="text-sm text-gray-600 mt-2">
                      Avg time from detection to action
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Guardrail Hits */}
            {guardrailHits && (
              <div className="bg-white p-6 rounded-lg shadow">
                <h2 className="text-xl font-bold text-gray-900 mb-4">
                  Guardrail Enforcement
                  <span className="ml-2 text-sm font-normal text-green-600">
                    ✓ System is bounded
                  </span>
                </h2>
                <p className="text-sm text-gray-600 mb-4">
                  Total blocked: {guardrailHits.total_blocked} actions
                </p>
                {guardrailHits.guardrail_hits.length > 0 && (
                  <div className="space-y-2">
                    {guardrailHits.guardrail_hits.map((hit: any, idx: number) => (
                      <div key={idx} className="flex justify-between p-3 bg-gray-50 rounded">
                        <span className="text-sm text-gray-700">{hit.reason || "Unknown"}</span>
                        <span className="text-sm font-semibold">{hit.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Hinglish Messages Tab */}
        {activeTab === "hinglish" && hinglishExamples && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-xl font-bold text-gray-900 mb-2">
                Hinglish Recovery Messages
                <span className="ml-2 text-sm font-normal text-blue-600">
                  Standout Feature
                </span>
              </h2>
              <p className="text-sm text-gray-600 mb-6">
                Natural Hindi+English code-mixed messages matching how Indian merchants communicate
              </p>

              {hinglishExamples.examples.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <p>No Hinglish messages generated yet.</p>
                  <p className="text-sm mt-2">Run the pipeline to see examples.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {hinglishExamples.examples.slice(0, 3).map((example: any, idx: number) => (
                    <div key={idx} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex justify-between items-start mb-3">
                        <span className="text-xs font-semibold text-blue-600 uppercase">
                          {example.action}
                        </span>
                        <span className="text-xs text-gray-500">
                          {example.character_count} chars
                        </span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-blue-50 p-4 rounded">
                          <p className="text-xs font-semibold text-gray-600 mb-2">
                            Hinglish
                          </p>
                          <p className="text-sm text-gray-900">{example.hinglish_message}</p>
                        </div>
                        <div className="bg-gray-50 p-4 rounded">
                          <p className="text-xs font-semibold text-gray-600 mb-2">
                            English
                          </p>
                          <p className="text-sm text-gray-700">{example.english_message}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Audit Trail Tab */}
        {activeTab === "audit" && auditTrail && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="p-6 border-b">
              <h2 className="text-xl font-bold text-gray-900">Audit Trail</h2>
              <p className="text-sm text-gray-600 mt-1">
                Full reasoning for every action
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Issue
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Action
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="px-6 py-3"></th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {auditTrail.entries.map((entry: any) => (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {entry.target_type}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {entry.detected_issue}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        {entry.executed_action}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`px-2 py-1 text-xs font-semibold rounded-full ${
                            entry.status === "executed"
                              ? "bg-green-100 text-green-800"
                              : entry.status === "blocked_by_guardrail"
                              ? "bg-orange-100 text-orange-800"
                              : "bg-gray-100 text-gray-800"
                          }`}
                        >
                          {entry.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right text-sm">
                        <button
                          onClick={() => setSelectedEntry(entry)}
                          className="text-blue-600 hover:text-blue-900"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Modal for viewing full reasoning */}
      {selectedEntry && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">
                    Full Reasoning Log
                  </h3>
                  <p className="text-sm text-gray-600 mt-1">ID: {selectedEntry.id}</p>
                </div>
                <button
                  onClick={() => setSelectedEntry(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="p-6">
              <pre className="text-xs bg-gray-900 text-green-400 p-4 rounded overflow-x-auto leading-relaxed">
                {JSON.stringify(selectedEntry.reasoning_log, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
