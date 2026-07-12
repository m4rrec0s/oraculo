import { useEffect, useState, useCallback } from "react";
import { Users, RefreshCw, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";
import type { AnaSession, AnaSessionsResponse } from "@/lib/api";
import { isoTimeAgo } from "@/lib/utils";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";

const STATUS_TONE: Record<string, string> = {
  active: "text-success",
  archived: "text-text-secondary",
  blocked: "text-destructive",
};

export default function AnaSessionsPage() {
  const [sessions, setSessions] = useState<AnaSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const limit = 50;
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data: AnaSessionsResponse = await api.getAnaSessions(limit, offset);
      setSessions(data.sessions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [limit, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-midground" />
          <h2 className="font-mondwest text-display uppercase tracking-[0.12em] text-midground">
            Sessões da Ana
          </h2>
        </div>
        <Button
          ghost
          size="icon"
          onClick={() => void load()}
          aria-label="Atualizar"
        >
          <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="text-destructive text-sm py-4">{error}</CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12 text-sm text-text-secondary">
          <Spinner />
          <span className="ml-2">Carregando…</span>
        </div>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="text-text-secondary text-sm py-6">
            Nenhuma sessão da Ana ainda.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="font-mondwest text-display uppercase tracking-[0.12em]">
              {sessions.length} sessão(ões)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-text-tertiary uppercase text-xs tracking-wider">
                  <tr className="border-b border-current/10">
                    <th className="text-left px-4 py-2">Cliente</th>
                    <th className="text-left px-4 py-2">Status</th>
                    <th className="text-right px-4 py-2">Msgs</th>
                    <th className="text-left px-4 py-2">Última mensagem</th>
                    <th className="text-right px-4 py-2">Atividade</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr
                      key={s.session_id}
                      className="border-b border-current/5 hover:bg-current/5"
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium">{s.cell || s.session_id}</div>
                        <div className="text-text-tertiary text-xs truncate max-w-[12rem]">
                          {s.session_id}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={STATUS_TONE[s.status] ?? "text-text-secondary"}>
                          {s.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">{s.message_count}</td>
                      <td className="px-4 py-3 max-w-[28rem] truncate text-text-secondary">
                        {s.last_message ? (
                          <span className="inline-flex items-center gap-1">
                            <MessageSquare className="h-3 w-3 shrink-0" />
                            {s.last_message}
                          </span>
                        ) : (
                          <span className="text-text-tertiary">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-text-secondary">
                        {s.last_message_at ? isoTimeAgo(s.last_message_at) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-current/10">
              <Button
                ghost
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - limit))}
              >
                Anterior
              </Button>
              <Button
                ghost
                disabled={sessions.length < limit}
                onClick={() => setOffset((o) => o + limit)}
              >
                Próximo
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
