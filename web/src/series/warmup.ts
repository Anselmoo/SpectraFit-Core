export interface WarmupLine { backend:string; coldMs:number; hotMs:number; rows:{n:number;perRun:number;backend:string}[]; }
export function warmupLines(f:any, solverIds:string[]):WarmupLine[] {
  return solverIds.filter(b=>f.profiles?.[b]?.warmup?.curve).map(b=>{
    const w=f.profiles[b].warmup;
    return { backend:b, coldMs:w.coldMs, hotMs:w.hotMs,
      rows:w.curve.map((p:any)=>({n:p.x, perRun:p.y, backend:b})) };
  });
}
