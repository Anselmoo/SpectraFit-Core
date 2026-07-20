export interface PullEntry { backend:string; pulls:number[]; coverage:number|null; absent:boolean; }
export function pullSeries(f:any, solverIds:string[]):PullEntry[] {
  return solverIds.filter(b=>f.profiles?.[b]?.uncertainty).map(b=>{
    const u=f.profiles[b].uncertainty;
    const absent = u.coverage == null;
    return { backend:b, pulls:u.pulls, coverage:u.coverage, absent };
  });
}
