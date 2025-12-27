import Link from "next/link";

import LoudnessBar from "@/components/LoudnessBar";
import Tag from "@/components/Tag";
import Transcript from "@/components/Transcript";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card } from "@/components/ui/card";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { CallRecord } from "@/lib/sample-data";
import { getTagTone } from "@/lib/tag-tone";

type CallCardProps = {
  call: CallRecord;
  defaultOpen?: boolean;
};

export default function CallCard({ call, defaultOpen = false }: CallCardProps) {
  return (
    <Accordion type="single" collapsible defaultValue={defaultOpen ? call.id : undefined}>
      <AccordionItem value={call.id} className="border-none">
        <Card className="rounded-lg">
          <AccordionTrigger className="px-6 py-4">
            <div className="flex w-full items-start justify-between gap-6">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Call summary</p>
                <h3 className="text-lg font-semibold">{call.summary}</h3>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  <span>{formatDateTime(call.createdAt)}</span>
                  <span>{formatDuration(call.durationSec)}</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {call.tags.map((tag) => (
                    <Tag key={tag} label={tag} tone={getTagTone(tag)} />
                  ))}
                </div>
              </div>
              <Link
                className="text-sm text-muted-foreground hover:text-foreground"
                href={`/calls/${call.id}`}
                aria-label="Open call details"
              >
                Open
              </Link>
            </div>
          </AccordionTrigger>
          <AccordionContent className="px-6">
            <div className="flex flex-wrap gap-2">
              {call.impliedName && <Tag label={`Implied name: ${call.impliedName}`} />}
              {call.externalNumber && <Tag label={`External: ${call.externalNumber}`} />}
              {call.outcome?.reason && <Tag label={`Lost reason: ${call.outcome.reason}`} tone="warn" />}
            </div>
            <div className="mt-4">
              <LoudnessBar durationSec={call.audio.durationSec} progress={call.audio.previewProgress} />
            </div>
            <div className="mt-4">
              <Transcript segments={call.transcript} />
            </div>
          </AccordionContent>
        </Card>
      </AccordionItem>
    </Accordion>
  );
}
