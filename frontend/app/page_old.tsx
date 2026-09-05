"use client";

import { useEffect, useState } from "react";
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

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    try {
      const [funnel, category, falsePos, lat, guardrail, audit, hinglish, statsData] =
        await Promise.all([
          fetch(`${API_BASE}/funnel`).then((r) => r.json()),
          fetch(`${API_BASE}/recovery-by-category`).then((r) => r.json()),
          fetch(`${API_BASE}/false-positive-rate`).then((r) => r.json()),
          fetch(`${API_BASE}/latency`).then((r) => r.json()),
          fetch(`${API_BASE}/guardrail-hits`).then((r) => r.json()),
          fetch(`${API_BASE}/audit-trail?limit=20`).then((r) => r.json()),
          fetch(`${API_BASE}/hinglish-examples`).then((r) => r.json()),
          fetch(`${API_BASE}/stats`).then((r) => r.json()),
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
    }
  };

  const formatCurrency = (paise: number) => {
    return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
  };

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
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Stats Cards */}
            {stats && (
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
            )}

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
  );
}
