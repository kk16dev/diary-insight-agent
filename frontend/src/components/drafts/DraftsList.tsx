import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Draft } from "@/services/draftsService"

interface DraftsListProps {
  drafts: Draft[]
  selectedDate: string | null
  onSelectDate: (date: string) => void
  isLoading: boolean
  error: string | null
}

export function DraftsList({
  drafts,
  selectedDate,
  onSelectDate,
  isLoading,
  error,
}: DraftsListProps) {
  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-red-500">{error}</p>
      </div>
    )
  }

  if (drafts.length === 0) {
    return (
      <div className="p-4">
        <p className="text-gray-500">No drafts found</p>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-2">
      <h2 className="text-xl font-bold mb-4">Draft List</h2>
      {drafts.map((draft) => (
        <Card
          key={draft.date}
          className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
            selectedDate === draft.date ? "border-blue-500 border-2 bg-blue-50" : ""
          }`}
          onClick={() => onSelectDate(draft.date)}
        >
          <div className="font-semibold text-lg">{draft.date}</div>
          <div className="text-sm text-gray-500 mt-1">
            Extracted: {new Date(draft.extracted_at).toLocaleString()}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            Status: {draft.status}
          </div>
        </Card>
      ))}
    </div>
  )
}