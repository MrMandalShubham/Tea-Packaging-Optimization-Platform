/**
 * Typed API client for the Tea Packaging Optimization backend.
 *
 * All response types are inferred from the backend Pydantic schemas.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

export interface SimulationInput {
  tea_density: number;
  package_weight: number;
  shipment_quantity: number;
  shipment_type: "total_weight" | "per_container";
  package_shape: "square" | "round";
  packaging_material: "paper" | "plastic" | "metal";
  target_market?: string;
}

export interface SimulationCreateResponse {
  id: string;
  status: string;
  message: string;
}

export interface PackageOption {
  id: string;
  simulation_id: string;
  volume_cm3: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  shape: string;
  material: string;
  fill_ratio: number;
  material_usage_sqm: number;
  cost_estimate: number;
  is_best: boolean;
  rank: number;
}

export interface CartonConfig {
  id: string;
  simulation_id: string;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  units_per_carton: number;
  carton_weight_kg: number;
  board_grade: string;
}

export interface PalletConfig {
  id: string;
  simulation_id: string;
  cartons_per_layer: number;
  layers: number;
  cartons_per_pallet: number;
  pallet_height_m: number;
  total_weight_kg: number;
}

export interface ContainerConfig {
  id: string;
  simulation_id: string;
  container_type: string;
  cartons_per_container: number;
  utilization_pct: number;
  empty_space_m3: number;
  total_units: number;
  freight_cost: number;
  is_best: boolean;
}

export interface CompareRow {
  parameter_name: string;
  current_value: number;
  ai_value: number;
  improvement_pct: number;
}

export interface CompareResponse {
  simulation_id?: string;
  rows: CompareRow[];
  packaging_cost_current: number;
  packaging_cost_ai: number;
  freight_cost_current: number;
  freight_cost_ai: number;
  total_cost_current: number;
  total_cost_ai: number;
  total_savings: number;
}

export interface SimulationDetail {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  inputs: SimulationInput | null;
  best_package: PackageOption | null;
  package_alternatives: PackageOption[];
  carton: CartonConfig | null;
  pallet: PalletConfig | null;
  best_container: ContainerConfig | null;
  container_alternatives: ContainerConfig[];
  comparison: CompareResponse | null;
}

export interface SimulationListItem {
  id: string;
  status: string;
  tea_density: number | null;
  package_weight: number | null;
  shipment_quantity: number | null;
  total_cost: number | null;
  total_savings: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedSimulations {
  items: SimulationListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardData {
  total_simulations: number;
  total_savings: number;
  average_container_utilization: number;
  recent_simulations: SimulationListItem[];
}

export interface PackageOptimizeResponse {
  best_package: PackageOption;
  alternatives: PackageOption[];
}

export interface CartonOptimizeResponse {
  config: CartonConfig;
}

export interface PalletOptimizeResponse {
  config: PalletConfig;
}

export interface ContainerOptimizeResponse {
  best_container: ContainerConfig;
  alternatives: ContainerConfig[];
}

export interface CompareRequest {
  simulation_id?: string;
  ship_quantity: number;
  tea_density: number;
  package_weight: number;
  current_package_length_mm?: number;
  current_package_width_mm?: number;
  current_package_height_mm?: number;
  current_carton_length_mm?: number;
  current_carton_width_mm?: number;
  current_carton_height_mm?: number;
  current_units_per_carton?: number;
  current_cartons_per_pallet?: number;
  current_containers?: number;
  current_packaging_cost?: number;
  current_freight_cost?: number;
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// ── Public API ────────────────────────────────────────────────────────────────

export const api = {
  // Dashboard
  getDashboard: () =>
    request<DashboardData>("/api/dashboard"),

  // Simulations
  createSimulation: (input: SimulationInput) =>
    request<SimulationCreateResponse>("/api/simulation", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listSimulations: (page = 1, pageSize = 20) =>
    request<PaginatedSimulations>(
      `/api/simulation?page=${page}&page_size=${pageSize}`
    ),

  getSimulation: (id: string) =>
    request<SimulationDetail>(`/api/simulation/${id}`),

  // Standalone optimizations
  optimizePackage: (input: {
    tea_density: number;
    package_weight: number;
    package_shape: string;
    packaging_material: string;
  }) =>
    request<PackageOptimizeResponse>("/api/optimize/package", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizeCarton: (input: {
    package_length_mm: number;
    package_width_mm: number;
    package_height_mm: number;
    package_weight_g: number;
    shipment_quantity: number;
  }) =>
    request<CartonOptimizeResponse>("/api/optimize/carton", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizePallet: (input: {
    carton_length_mm: number;
    carton_width_mm: number;
    carton_height_mm: number;
    carton_weight_kg: number;
  }) =>
    request<PalletOptimizeResponse>("/api/optimize/pallet", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  optimizeContainer: (input: {
    carton_length_mm: number;
    carton_width_mm: number;
    carton_height_mm: number;
    cartons_per_pallet: number;
    pallet_height_m: number;
    shipment_quantity: number;
    units_per_carton?: number;
  }) =>
    request<ContainerOptimizeResponse>("/api/optimize/container", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  compare: (input: CompareRequest) =>
    request<CompareResponse>("/api/compare", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // AI Analysis
  getAIAnalysis: (simulationId: string) =>
    request<AIAnalysis>(`/api/simulation/${simulationId}/ai`),
};

// ── AI Types ──────────────────────────────────────────────────────────────────

export interface StageValidation {
  stage: string;
  status: "valid" | "warning" | "invalid";
  message: string;
}

export interface AIAnalysis {
  validations: StageValidation[];
  summary: string;
  error?: string;
}
