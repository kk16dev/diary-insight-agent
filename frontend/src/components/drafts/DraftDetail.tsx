import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer"
import { DraftDetail as DraftDetailType } from "@/services/draftsService"

interface DraftDetailProps {
  draftDetail: DraftDetailType | null
  isLoading: boolean
  error: string | null
}

export function DraftDetail({ draftDetail, isLoading, error }: DraftDetailProps) {
  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-96 w-full" />
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

  if (!draftDetail) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Select a draft to view details</p>
      </div>
    )
  }

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-2">{draftDetail.date}</h1>
      <p className="text-sm text-gray-500 mb-4">
        Extracted: {new Date(draftDetail.metadata.extracted_at).toLocaleString()}
      </p>

      <Tabs defaultValue="original" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="original">Original Diary</TabsTrigger>
          <TabsTrigger value="references">References</TabsTrigger>
          <TabsTrigger value="ideas">Ideas</TabsTrigger>
          <TabsTrigger value="goals">Goals</TabsTrigger>
        </TabsList>

        <TabsContent value="original">
          <Card>
            <CardHeader>
              <CardTitle>Original Diary</CardTitle>
            </CardHeader>
            <CardContent>
              <MarkdownRenderer content={draftDetail.original} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="references">
          <Card>
            <CardHeader>
              <CardTitle>References</CardTitle>
            </CardHeader>
            <CardContent>
              {draftDetail.references ? (
                <MarkdownRenderer content={draftDetail.references} />
              ) : (
                <p className="text-gray-500">No references</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ideas">
          <Card>
            <CardHeader>
              <CardTitle>Ideas</CardTitle>
            </CardHeader>
            <CardContent>
              {draftDetail.ideas ? (
                <MarkdownRenderer content={draftDetail.ideas} />
              ) : (
                <p className="text-gray-500">No ideas</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="goals">
          <Card>
            <CardHeader>
              <CardTitle>Goals</CardTitle>
            </CardHeader>
            <CardContent>
              {draftDetail.goals ? (
                <MarkdownRenderer content={draftDetail.goals} />
              ) : (
                <p className="text-gray-500">No goals</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}