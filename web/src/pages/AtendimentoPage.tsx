import { useEffect, useState, useCallback } from "react";
import { Users, RefreshCw, MessageSquare, Pencil, Power, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { PersonaSession, PersonaSessionsResponse, PersonaInfo } from "@/lib/api";
import { isoTimeAgo } from "@/lib/utils";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";

const STATUS_TONE: Record<string, string> = {
  active: "text-success",
  archived: "text-text-secondary",
  blocked: "text-destructive",
};

export default function AtendimentoPage() {
  const [personas, setPersonas] = useState<PersonaInfo[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [sessions, setSessions] = useState<PersonaSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [personasLoading, setPersonasLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<Set<string>>(new Set());
  const limit = 50;
  const [offset, setOffset] = useState(0);

  const loadPersonas = useCallback(async () => {
    setPersonasLoading(true);
    try {
      const data = await api.getPersonaPersonas();
      const list = data.personas ?? [];
      setPersonas(list);
      // Auto-seleciona a primeira persona se nenhuma estiver selecionada
      setSelectedPersona((cur) => cur ?? list[0]?.persona ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPersonasLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    if (!selectedPersona) return;
    setLoading(true);
    setError(null);
    try {
      const data: PersonaSessionsResponse = await api.getPersonaSessions(selectedPersona, limit, offset);
      setSessions(data.sessions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedPersona, limit, offset]);

  useEffect(() => {
    void loadPersonas();
  }, [loadPersonas]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectPersona = (p: string) => {
    setSelectedPersona(p);
    setOffset(0);
  };

  const run = (id: string, fn: () => Promise<unknown>) => {
    setActing((s) => new Set(s).add(id));
    (async () => {
      try {
        await fn();
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setActing((s) => {
          const n = new Set(s);
          n.delete(id);
          return n;
        });
      }
    })();
  };

  const onRename = (s: PersonaSession) => {
    const name = window.prompt("Novo nome da sessão:", s.session_label || s.cell);
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    return run(s.session_id, () => api.renamePersonaSession(s.session_id, trimmed));
  };
  const onToggle = (s: PersonaSession) =>
    run(s.session_id, () => api.togglePersonaSession(s.session_id));
  const onDelete = (s: PersonaSession) => {
    if (!window.confirm(`Excluir sessão ${s.session_id}?`)) return;
    return run(s.session_id, () => api.deletePersonaSession(s.session_id));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-midground" />
          <h2 className="font-mondwest text-display uppercase tracking-[0.12em] text-midground">
            Atendimento
          </h2>
        </div>
        <Button
          ghost
          size="icon"
          onClick={() => {
            void loadPersonas();
            void load();
          }}
          aria-label="Atualizar"
        >
          <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
        </Button>
      </div>

      {/* Passo 1: escolher persona */}
      <Card>
        <CardHeader>
          <CardTitle className="font-mondwest text-display uppercase tracking-[0.12em]">
            Personas
          </CardTitle>
        </CardHeader>
        <CardContent>
          {personasLoading ? (
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <Spinner />
              <span>Carregando personas…</span>
            </div>
          ) : personas.length === 0 ? (
            <p className="text-text-secondary text-sm">Nenhuma persona com sessões ainda.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {personas.map((p) => {
                const active = p.persona === selectedPersona;
                return (
                  <Button
                    key={p.persona}
                    variant={active ? "default" : "outline"}
                    size="sm"
                    onClick={() => selectPersona(p.persona)}
                    className={active ? "" : "text-text-secondary"}
                  >
                    {p.persona}
                    <span className="ml-2 text-xs opacity-70">{p.session_count}</span>
                  </Button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <Card>
          <CardContent className="text-destructive text-sm py-4">{error}</CardContent>
        </Card>
      )}

      {!selectedPersona ? (
        <Card>
          <CardContent className="text-text-secondary text-sm py-6">
            Selecione uma persona acima para ver suas sessões.
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="flex items-center justify-center py-12 text-sm text-text-secondary">
          <Spinner />
          <span className="ml-2">Carregando…</span>
        </div>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="text-text-secondary text-sm py-6">
            Nenhuma sessão para “{selectedPersona}” ainda.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="font-mondwest text-display uppercase tracking-[0.12em]">
              {sessions.length} sessão(ões) · {selectedPersona}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-text-tertiary uppercase text-xs tracking-wider">
                   <tr className="border-b border-current/10">
                     <th className="text-left px-4 py-2">Cliente</th>
                     <th className="text-left px-4 py-2">Status</th>
                     <th className="text-left px-4 py-2">Última mensagem</th>
                     <th className="text-right px-4 py-2">Atividade</th>
                     <th className="text-right px-4 py-2">Ações</th>
                   </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr
                      key={s.session_id}
                      className="border-b border-current/5 hover:bg-current/5"
                    >
                       <td className="px-4 py-3">
                         <div className="font-medium">{s.session_label || s.cell}</div>
                         <div className="text-text-tertiary text-xs truncate max-w-[12rem]">
                           {s.session_id}
                         </div>
                       </td>
                       <td className="px-4 py-3">
                         <span className={STATUS_TONE[s.status] ?? "text-text-secondary"}>
                           {s.status}
                         </span>
                       </td>
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
                       <td className="px-4 py-3 text-right">
                         <div className="flex items-center justify-end gap-1">
                           <Button
                             ghost
                             size="icon"
                             aria-label="Editar nome"
                             disabled={acting.has(s.session_id)}
                             onClick={() => void onRename(s)}
                           >
                             <Pencil className="h-4 w-4" />
                           </Button>
                           <Button
                             ghost
                             size="icon"
                             aria-label="Fechar/Abrir"
                             disabled={acting.has(s.session_id)}
                             onClick={() => void onToggle(s)}
                           >
                             <Power className="h-4 w-4" />
                           </Button>
                           <Button
                             ghost
                             size="icon"
                             aria-label="Excluir"
                             disabled={acting.has(s.session_id)}
                             onClick={() => void onDelete(s)}
                           >
                             <Trash2 className="h-4 w-4 text-destructive" />
                           </Button>
                         </div>
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
