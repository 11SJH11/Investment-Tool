// Small PDF document writer: selectable built-in-font text + chart JPEGs.
// No indicator, price, return or evidence calculation belongs in this module.
const bytes = text => new TextEncoder().encode(text);
const printable = text => String(text).replace(/[^\x20-\x7e]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4,'0')}`);
const literal = text => String(text).replace(/[\\()]/g, '\\$&');
export class ResearchPdf {
  constructor() { this.pages=[]; }
  page(title, lines=[], image=null) {
    // Landscape A4, readable 10pt text. Long evidence continues on labelled pages.
    title=printable(title);
    const longTitle=title.length>84;
    if(longTitle){lines=['Title: '+title,...lines];title=title.slice(0,81)+'...';}
    let page={title,lines:[],image:null};this.pages.push(page);
    for(const value of lines) for(const line of String(value).split('\n')) {
      const parts=printable(line).match(/.{1,115}/g)||[''];
      for(const part of parts) {if(page.lines.length>=32){page={title:title+' (continued)',lines:[],image:null};this.pages.push(page);}page.lines.push(part);}
    }
    if(image){if(page.lines.length>5){page={title:title+' / chart',lines:[],image:null};this.pages.push(page);}page.image=image;}
  }
  blob() {
    const objects=[null,null,bytes('<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>')];
    const add=value=>{objects.push(typeof value==='string'?bytes(value):value);return objects.length;};
    const stream=(head,data)=>new Blob([bytes(`<< ${head} /Length ${data.length} >>\nstream\n`),data,bytes('\nendstream')]);
    const ids=[];
    for(const page of this.pages){
      let commands=`BT /F1 15 Tf 30 560 Td (${literal(page.title)}) Tj ET\n`;
      page.lines.forEach((line,i)=>{commands+=`BT /F1 10 Tf 30 ${535-i*15} Td (${literal(line)}) Tj ET\n`;});
      let resource='';
      if(page.image){const im=page.image;const raw=Uint8Array.from(atob(im.data.split(',')[1]),c=>c.charCodeAt(0));const id=add(stream(`/Type /XObject /Subtype /Image /Width ${im.width} /Height ${im.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`,raw));resource=`/XObject << /Chart ${id} 0 R >>`;
        const width=782,height=Math.min(435,width*im.height/im.width);commands+=`q ${width} 0 0 ${height} 30 ${Math.max(30,475-height)} cm /Chart Do Q\n`;}
      const content=add(stream('',bytes(commands)));
      ids.push(add(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> ${resource} >> /Contents ${content} 0 R >>`));
    }
    objects[0]=bytes('<< /Type /Catalog /Pages 2 0 R >>');objects[1]=bytes(`<< /Type /Pages /Kids [${ids.map(id=>`${id} 0 R`).join(' ')}] /Count ${ids.length} >>`);
    const chunks=[bytes('%PDF-1.4\n')],offsets=[0];let position=chunks[0].length;
    objects.forEach((object,i)=>{offsets.push(position);const chunk=new Blob([bytes(`${i+1} 0 obj\n`),object,bytes('\nendobj\n')]);chunks.push(chunk);position+=chunk.size;});
    const xref=`xref\n0 ${objects.length+1}\n0000000000 65535 f \n${offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${position}\n%%EOF\n`;
    return new Blob([...chunks,bytes(xref)],{type:'application/pdf'});
  }
}
export function evidenceLines(review) {
  const lines=[];
  for(const [group,fields] of Object.entries(review.evidence||{}))for(const field of fields)lines.push(`${group} / ${field.label}: ${field.value==null?'Not recorded':typeof field.value==='object'?JSON.stringify(field.value):field.value} [${field.provenance||'Not recorded'}] ${field.status||''}`);
  for(const series of review.series||[])lines.push(`${series.label} (${series.timeframe}) / ${series.role||'strategy evidence'} / ${series.provenance||'reconstructed'}`);
  for(const level of review.levels||[])lines.push(`${level.label}: ${level.value} / ${level.provenance||'recorded'}`);
  return [...lines,...(review.warnings||[]).map(w=>'Warning: '+w)];
}

export function documentFields(value, prefix='') {
  if(value==null)return [`${prefix}: Not recorded`];
  if(typeof value!=='object')return [`${prefix}: ${String(value)}`];
  return Object.entries(value).flatMap(([key,item])=>documentFields(item,prefix?`${prefix}.${key}`:key));
}
