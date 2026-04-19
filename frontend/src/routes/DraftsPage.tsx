"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { DraftsList } from "@/components/drafts/DraftsList"
import { DraftDetail } from "@/components/drafts/DraftDetail"
import {
  getDrafts,
  getDraftDetail,
  Draft,
  DraftDetail as DraftDetailType,
} from "@/services/draftsService"

export default function DraftsPage() {
  const { isAuthenticated, signIn, user } = useAuth()
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [draftDetail, setDraftDetail] = useState<DraftDetailType | null>(null)
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-4xl">Please sign in</p>
        <Button onClick={() => signIn()}>Sign In</Button>
      </div>
    )
  }

  useEffect(() => {
    async function loadDrafts() {
      setIsLoadingList(true)
      setError(null)
      try {
        const idToken = user?.id_token
        if (!idToken) throw new Error("No ID token")

        const data = await getDrafts(idToken)
        setDrafts(data.drafts)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load drafts")
      } finally {
        setIsLoadingList(false)
      }
    }
    loadDrafts()
  }, [user])

  useEffect(() => {
    async function loadDetail() {
      if (!selectedDate) {
        setDraftDetail(null)
        return
      }

      setIsLoadingDetail(true)
      setError(null)
      try {
        const idToken = user?.id_token
        if (!idToken) throw new Error("No ID token")

        const data = await getDraftDetail(selectedDate, idToken)
        setDraftDetail(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load draft detail")
      } finally {
        setIsLoadingDetail(false)
      }
    }
    loadDetail()
  }, [selectedDate, user])

  return (
    <div className="flex h-full">
      <div className="w-1/3 border-r overflow-y-auto">
        <DraftsList
          drafts={drafts}
          selectedDate={selectedDate}
          onSelectDate={setSelectedDate}
          isLoading={isLoadingList}
          error={error}
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        <DraftDetail
          draftDetail={draftDetail}
          isLoading={isLoadingDetail}
          error={error}
        />
      </div>
    </div>
  )
}