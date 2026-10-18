/**
 * Wire types for the FastAPI backend. Field names are snake_case on purpose: they mirror the
 * JSON the backend emits, so the client layer stays a thin, auditable translation of it.
 */

export type Role = "patient" | "clinician";

export interface AuthMe {
  id: string;
  role: Role;
  display_name: string | null;
}

/** The API's own wording is `moderate`; alerts and the database enum say `medium`. */
export type RiskLevel = "low" | "moderate" | "high";
export type WireRisk = "low" | "medium" | "moderate" | "high";

export type CheckinStatus = "pending" | "analyzed" | "analysis_failed";
export type RiskSource = "keyword" | "llm" | "both" | "fallback";
export type Confidence = "low" | "medium" | "high";

export const SYMPTOM_KEYS = [
  "sleep",
  "appetite",
  "energy",
  "anxiety",
  "concentration",
  "social_withdrawal",
  "irritability",
] as const;

export type SymptomKey = (typeof SYMPTOM_KEYS)[number];

/** 0 = not mentioned, 1–3 = how much it came through. Null means "not stated". */
export type Symptoms = Record<SymptomKey, number | null>;

export interface Analysis {
  mood_score: number;
  emotions: string[];
  symptoms: Symptoms;
  risk_level: RiskLevel;
  risk_evidence: string | null;
  summary: string;
  confidence: Confidence;
}

/** `POST /api/checkins` response. The transcript is deliberately not echoed back. */
export interface CheckinResult {
  checkin_id: string;
  status: CheckinStatus;
  analysis: Analysis | null;
  final_risk: RiskLevel;
  risk_source: RiskSource;
  show_crisis_resources: boolean;
}

export interface CheckinSummary {
  checkin_id: string;
  created_at: string;
  transcript: string | null;
  note: string | null;
  status: CheckinStatus;
  risk: RiskLevel | null;
  summary: string | null;
}

export interface CheckinPage {
  items: CheckinSummary[];
  limit: number;
  offset: number;
}

export interface ConsentLink {
  consent_id: string;
  clinician_id: string;
  clinician_name: string | null;
  granted_at: string;
}

/** Derived client-side: the backend answers with the list of active links. */
export interface ConsentStatus {
  hasConsent: boolean;
  clinicianName: string | null;
  grantedAt: string | null;
}

export interface InviteCreated {
  invite_id: string;
  code: string;
  expires_at: string;
}

export interface InviteRow {
  invite_id: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  used_by: string | null;
}

export interface TranscribeResult {
  transcript: string;
  duration_seconds: number;
}

export interface PatientSummary {
  patient_id: string;
  display_name: string | null;
  consent_granted_at: string;
  last_checkin_at: string | null;
  last_risk: RiskLevel | null;
  last_summary: string | null;
  open_alerts: number;
}

export interface PatientPage {
  items: PatientSummary[];
  total: number;
}

export interface TrendPoint {
  checkin_id: string;
  created_at: string;
  mood_score: number | null;
  risk: RiskLevel | null;
  risk_source: RiskSource | null;
  summary: string | null;
}

export interface Trend {
  patient_id: string;
  days: number;
  points: TrendPoint[];
  high_count: number;
  moderate_count: number;
  missing_analysis: number;
}

export interface CheckinDetail {
  checkin_id: string;
  patient_id: string;
  created_at: string;
  transcript: string | null;
  note: string | null;
  status: CheckinStatus;
  model: string | null;
  summary: string | null;
  risk: WireRisk | null;
  risk_source: string | null;
  confidence: string | null;
  evidence_quote: string | null;
  /** Not served today; honoured if the backend adds them. */
  evidence_start?: number | null;
  evidence_end?: number | null;
  mood_score: number | null;
  emotions: string[];
  symptoms: Partial<Record<string, number | null>>;
}

export interface Alert {
  alert_id: string;
  patient_id: string;
  patient_name: string | null;
  severity: "low" | "medium" | "high";
  message: string;
  created_at: string;
  acknowledged_at: string | null;
  analysis_id: string | null;
}

export interface AcknowledgedAlert {
  alert_id: string;
  acknowledged_at: string;
  acknowledged_by: string;
}

/** One place that turns either spelling into the app's word for a risk level. */
export function normalizeRisk(value: WireRisk | string | null | undefined): RiskLevel | null {
  if (value === "low" || value === "moderate" || value === "high") return value;
  if (value === "medium") return "moderate";
  return null;
}
