<script setup lang="ts">
// Sortable table for tabular data in replies (markdown tables, JSON row arrays, tool results).
import { ArrowDown, ArrowUp, ArrowUpDown } from '@lucide/vue'
import {
  type ColumnDef,
  createSortedRowModel,
  FlexRender,
  rowSortingFeature,
  type SortFn,
  tableFeatures,
  useTable,
} from '@tanstack/vue-table'
import { computed } from 'vue'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { TableRow as Row } from '@/lib/markdown'

const props = defineProps<{
  columns: string[]
  rows: Row[]
  caption?: string
}>()

// "1,204", "$3.50" and "98%" sort as numbers; everything else sorts as text.
function toNumber(v: unknown): number | null {
  if (typeof v === 'number') return v
  if (typeof v !== 'string' || !/^[-+]?[$€£]?\s?[\d,]*\.?\d+\s?%?$/.test(v.trim())) return null
  const n = Number(v.replace(/[^\d.+-]/g, ''))
  return Number.isFinite(n) ? n : null
}

const smartSort: SortFn<typeof features, Row> = (a, b, id) => {
  const x = a.getValue(id)
  const y = b.getValue(id)
  const nx = toNumber(x)
  const ny = toNumber(y)
  if (nx !== null && ny !== null) return nx - ny
  return String(x ?? '').localeCompare(String(y ?? ''), undefined, { numeric: true })
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
})

const columnDefs = computed<ColumnDef<typeof features, Row>[]>(() =>
  props.columns.map((name) => ({
    id: name,
    accessorFn: (row: Row) => row[name],
    header: name,
    cell: (info) => {
      const v = info.getValue()
      return v === null || v === undefined ? '—' : String(v)
    },
    sortFn: smartSort,
    sortUndefined: 'last' as const,
  })),
)

const table = useTable({
  features,
  get columns() {
    return columnDefs.value
  },
  data: computed(() => props.rows),
})

function ariaSort(dir: false | 'asc' | 'desc') {
  return dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'
}
</script>

<template>
  <div class="my-3 overflow-hidden rounded-lg border">
    <div class="max-h-96 overflow-auto">
      <Table>
        <TableCaption v-if="caption" class="sr-only">{{ caption }}</TableCaption>
        <TableHeader class="sticky top-0 z-10 bg-muted/80 backdrop-blur">
          <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
            <TableHead
              v-for="header in group.headers"
              :key="header.id"
              :aria-sort="ariaSort(header.column.getIsSorted())"
              class="whitespace-nowrap"
            >
              <button
                v-if="!header.isPlaceholder"
                type="button"
                class="-mx-1 inline-flex items-center gap-1 rounded px-1 font-medium hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                @click="header.column.getToggleSortingHandler()?.($event)"
              >
                <FlexRender :header="header" />
                <ArrowUp
                  v-if="header.column.getIsSorted() === 'asc'"
                  class="size-3.5"
                  aria-hidden="true"
                />
                <ArrowDown
                  v-else-if="header.column.getIsSorted() === 'desc'"
                  class="size-3.5"
                  aria-hidden="true"
                />
                <ArrowUpDown v-else class="size-3.5 opacity-40" aria-hidden="true" />
              </button>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell v-for="cell in row.getAllCells()" :key="cell.id" class="tabular-nums">
              <FlexRender :cell="cell" />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <p class="border-t bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
      {{ rows.length }} {{ rows.length === 1 ? 'row' : 'rows' }} · click a header to sort
    </p>
  </div>
</template>
