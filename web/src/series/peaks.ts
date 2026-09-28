export interface PeakRow { x:number; y:number; label:string; }
export function peakRows(f:{x:number[]; peaks?:{label:string;y:number[]}[]}):PeakRow[] {
  return (f.peaks ?? []).flatMap(p => f.x.map((xi,i)=>({x:xi,y:p.y[i],label:p.label})));
}
