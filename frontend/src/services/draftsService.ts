/**
 * Drafts Service
 * Handles fetching draft diary extractions from the backend API
 */

// Load API URL from aws-exports.json
let DRAFTS_API_URL = ""

// Dynamically load the API URL from aws-exports.json
async function loadApiUrl(): Promise<string> {
  if (DRAFTS_API_URL) {
    return DRAFTS_API_URL
  }

  try {
    const response = await fetch("/aws-exports.json")
    const config = await response.json()
    DRAFTS_API_URL = config.feedbackApiUrl ? `${config.feedbackApiUrl}drafts` : ""
    return DRAFTS_API_URL
  } catch (error) {
    console.error("Failed to load API URL from aws-exports.json:", error)
    throw new Error("Drafts API URL not configured")
  }
}

export interface Draft {
  date: string
  extracted_at: string
  status: string
}

export interface DraftDetail {
  date: string
  metadata: {
    extracted_at: string
    model_id: string
    extraction_status: string
  }
  original: string
  references: string
  ideas: string
  goals: string
}

export interface DraftsListResponse {
  drafts: Draft[]
}

/**
 * Get list of drafts
 *
 * @param idToken - Cognito ID token for authentication
 * @param dateFrom - Optional start date filter (YYYY-MM-DD)
 * @param dateTo - Optional end date filter (YYYY-MM-DD)
 * @returns Promise with list of drafts
 */
export async function getDrafts(
  idToken: string,
  dateFrom?: string,
  dateTo?: string
): Promise<DraftsListResponse> {
  try {
    const apiUrl = await loadApiUrl()

    const params = new URLSearchParams()
    if (dateFrom) params.append("date_from", dateFrom)
    if (dateTo) params.append("date_to", dateTo)

    const url = `${apiUrl}${params.toString() ? `?${params.toString()}` : ""}`

    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${idToken}`,
      },
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
    }

    const data: DraftsListResponse = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching drafts:", error)
    throw error
  }
}

/**
 * Get draft detail for a specific date
 *
 * @param date - Date string in YYYY-MM-DD format
 * @param idToken - Cognito ID token for authentication
 * @returns Promise with draft detail
 */
export async function getDraftDetail(
  date: string,
  idToken: string
): Promise<DraftDetail> {
  try {
    const apiUrl = await loadApiUrl()
    const url = `${apiUrl}/${date}`

    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${idToken}`,
      },
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.error || `HTTP error! status: ${response.status}`)
    }

    const data: DraftDetail = await response.json()
    return data
  } catch (error) {
    console.error("Error fetching draft detail:", error)
    throw error
  }
}