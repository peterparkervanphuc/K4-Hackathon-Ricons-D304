import fs from 'node:fs/promises';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const OUT = 'C:/Users/Admin/Downloads/K4-Hackathon-Ricons-D304-feature-GiangHoang/K4-Hackathon-Ricons-D304-feature-GiangHoang/codebase/demo_round_evidence_first.pptx';
const W = 1280, H = 720;
const C = { ink: '#111827', muted: '#64748B', line: '#CBD5E1', panel: '#F1F5F9', accent: '#0EA5E9', navy: '#0F172A', warn: '#B45309', white: '#FFFFFF' };

async function save(blob, path) { await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer())); }
function box(slide, left, top, width, height, fill = 'none', line = 'none') {
  return slide.shapes.add({ geometry: 'rect', position: { left, top, width, height }, fill, line: { style: 'solid', fill: line, width: line === 'none' ? 0 : 1 } });
}
function text(slide, value, left, top, width, height, size = 22, color = C.ink, bold = false, align = 'left') {
  const s = box(slide, left, top, width, height);
  s.text = value;
  s.text.style = { fontFace: 'Arial', fontSize: size, color, bold, alignment: align, verticalAlignment: 'middle' };
  return s;
}
function title(slide, n, value, kicker) {
  text(slide, `0${n}  /  06`, 62, 42, 150, 24, 14, C.accent, true);
  text(slide, value, 62, 77, 1080, 58, 38, C.navy, true);
  text(slide, kicker, 62, 140, 1060, 26, 17, C.muted);
  box(slide, 62, 178, 1156, 2, C.line);
}
function card(slide, left, top, width, height, heading, body, emphasis = false) {
  box(slide, left, top, width, height, emphasis ? '#E0F2FE' : C.panel, C.line);
  text(slide, heading, left + 20, top + 18, width - 40, 30, 20, emphasis ? '#075985' : C.navy, true);
  text(slide, body, left + 20, top + 58, width - 40, height - 76, 18, C.ink);
}
function evidence(slide, value, label, left, top, width) {
  box(slide, left, top, width, 106, '#FEF3C7', '#F59E0B');
  text(slide, value, left + 18, top + 14, width - 36, 47, 30, C.warn, true);
  text(slide, label, left + 18, top + 66, width - 36, 24, 15, C.warn);
}
function footer(slide, note) { text(slide, note, 62, 675, 1090, 20, 12, C.muted); text(slide, 'Demo round · 5 min + Q&A', 1008, 675, 210, 20, 12, C.muted, false, 'right'); }

const p = Presentation.create({ slideSize: { width: W, height: H } });

// 1. User & JTBD
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 1, 'Người dùng bị kẹt ở bước thực thi, không phải ở ý định', '45 giây · Nêu một job rõ ràng, có pain định lượng và nguồn kiểm chứng');
  text(s, 'CORE JTBD', 62, 214, 280, 24, 16, C.accent, true); text(s, '“Khi [tình huống], tôi muốn [hành động] để [kết quả đo được].”', 62, 248, 610, 86, 30, C.navy, true);
  card(s, 62, 380, 590, 200, 'Job executor', '[Vai trò cụ thể] · [bối cảnh] · [tần suất]\nKhông dùng persona chung chung.', true);
  evidence(s, '41 / 200 hội thoại', 'Pain signal — gắn link log / dashboard / ngày đo', 704, 215, 430);
  evidence(s, '17 / 25 người khảo sát', 'Validation signal — gắn form / script phỏng vấn', 704, 350, 430);
  footer(s, 'Chỉ giữ số đã truy xuất được. Nếu chưa có nguồn, thay bằng [ĐIỀN BẰNG CHỨNG].'); }

// 2. Why this feature
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 2, 'Chọn tính năng vì tác động đã được so sánh, không vì “ý tưởng đầu tiên”', '45 giây · Hiển thị trade-off và một ứng viên bị loại');
  text(s, 'ỨNG VIÊN', 74, 220, 270, 24, 15, C.muted, true); text(s, 'IMPACT', 640, 220, 150, 24, 15, C.muted, true); text(s, 'QUYẾT ĐỊNH', 930, 220, 190, 24, 15, C.muted, true);
  const rows = [ ['A. [Tính năng được chọn]', '[x%] / [n] evidence', 'CHỌN — giải pain lõi'], ['B. [Ứng viên 2]', '[x%] / [n] evidence', 'Loại — [lý do 1 dòng]'], ['C. [Ứng viên 3]', '[x%] / [n] evidence', 'Loại — [lý do 1 dòng]'] ];
  rows.forEach((r,i)=>{ const y=260+i*94; box(s,62,y,1090,74,i===0?'#E0F2FE':C.panel,C.line); text(s,r[0],78,y+18,490,34,22,C.navy,i===0); text(s,r[1],640,y+18,220,34,20,C.ink); text(s,r[2],930,y+18,205,34,18,i===0?'#075985':C.ink,i===0); });
  evidence(s, '[ĐIỀN 1 số quyết định]', 'Metric / quote khiến A thắng — phải truy xuất được', 62, 574, 500); footer(s, 'Nguồn: research log, clickstream, interview notes hoặc test result.'); }

// 3. Solution & live demo
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 3, 'Lát cắt nhỏ: một automation, hai case, một chất lượng có thể kiểm tra', '2 phút · Demo live; case khó phải cho thấy hệ thống xử lý lỗi');
  text(s, 'LÁT CẮT 1 CÂU', 62, 212, 260, 22, 15, C.accent, true); text(s, '[Người dùng] hoàn thành [job] trong [bước/kết quả] — không cần [công việc thủ công].', 62, 242, 1090, 52, 29, C.navy, true);
  card(s, 62, 338, 336, 204, '1. Case chuẩn', 'Input: [case happy path]\nDemo: [hành động 1–2]\nExpected: [kết quả đo được]');
  card(s, 434, 338, 336, 204, '2. Case khó', 'Input: [edge case / dữ liệu lỗi]\nDemo: [fallback / guardrail]\nExpected: [hệ thống nói/ làm gì]', true);
  card(s, 806, 338, 336, 204, 'Cost of error', 'Nếu sai: [hậu quả cụ thể]\nGuardrail: [cách chặn / giải thích / retry]');
  evidence(s, '[ĐIỀN quality bar 23:59 N1]', 'Ví dụ: pass ≥ __ / __ golden set · latency ≤ __', 62, 574, 680); footer(s, 'Không thay live demo bằng video khi app vẫn chạy được.'); }

// 4. Measured results
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 4, 'Kết quả được đọc cùng quality bar — và failure lớn nhất không bị che đi', '45 giây · Nếu chưa đạt, nêu nguyên nhân thay vì chỉ chọn số đẹp');
  evidence(s, '[__%] qua golden set', 'Đối chiếu trực tiếp với quality bar đã chốt 23:59 N1', 62, 220, 448);
  card(s, 548, 220, 604, 146, 'Quality bar đã cam kết', 'Target: [__ / __] · Actual: [__ / __]\nMethod: [link golden set / evaluator / thời điểm đo]', true);
  box(s,62,410,1090,176,'#FFF7ED','#FB923C'); text(s,'Failure đáng kể nhất',84,430,300,30,22,C.warn,true); text(s,'[Case lỗi] → [điều đã xảy ra] → [nguyên nhân giả thuyết] → [bằng chứng / log]',84,474,1010,64,21,C.ink);
  footer(s, 'Một failure thật tăng độ tin cậy hơn “100%” không có cách đo.'); }

// 5. Users say
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 5, 'Người dùng thật chỉ ra phần cần sửa — và chúng tôi đã sửa điều gì', '45 giây · Dùng nguyên văn quote, nêu rõ tên/vai và thay đổi sau validation');
  card(s,62,218,520,168,'“[Quote nguyên văn #1]”','— [Tên], [vai trò] · [ngày / phương thức validation]',true);
  card(s,636,218,520,168,'“[Quote nguyên văn #2]”','— [Tên], [vai trò] · [ngày / phương thức validation]',true);
  text(s,'THAY ĐỔI ĐÃ LÀM',62,438,330,24,15,C.accent,true);
  text(s,'Feedback → [thay đổi UX / logic #1]  |  Feedback → [thay đổi UX / logic #2]',62,478,1080,42,24,C.navy,true);
  evidence(s, '[ĐÍNH KÈM link validation]', 'Không dùng quote khen chung chung; cần ngữ cảnh và trace', 62, 562, 620); footer(s, 'Quote phải là nguyên văn và có thể mở lại bản ghi / form / note.'); }

// 6. Next week & Q&A
{ const s = p.slides.add(); s.background.fill = C.white; title(s, 6, 'Một tuần nữa: xử lý đúng những gì feedback và failure đang chỉ ra', '30 giây · 2–3 ưu tiên, rồi chuyển sang demo round 5 phút Q&A');
  const priorities = [ ['01', '[Ưu tiên 1]', 'Trỏ về: [feedback / failure]'], ['02', '[Ưu tiên 2]', 'Trỏ về: [feedback / failure]'], ['03', '[Ưu tiên 3]', 'Trỏ về: [feedback / failure]'] ];
  priorities.forEach((r,i)=>{const y=215+i*94; text(s,r[0],62,y,62,46,30,C.accent,true); text(s,r[1],150,y,360,46,25,C.navy,true); text(s,r[2],550,y,540,46,20,C.ink); box(s,62,y+68,1050,1,C.line);});
  box(s,62,522,1050,92,'#E0F2FE','#7DD3FC'); text(s,'Bài học lớn nhất',84,538,250,22,16,'#075985',true); text(s,'[Một câu: điều evidence đã buộc team thay đổi cách nghĩ / cách xây]',84,564,970,30,22,C.navy,true);
  text(s,'Q&A: giám khảo chạy 1 case lạ tại chỗ · mỗi thành viên nói ≥1 phần',62,640,1050,24,16,C.muted); footer(s, 'Checklist trước khi trình bày: link evidence mở được · demo có case khó · owner từng phần rõ ràng.'); }

for (let i = 0; i < p.slides.items.length; i++) await save(await p.export({ slide: p.slides.items[i], format: 'png', scale: 1 }), `C:/Users/Admin/Downloads/K4-Hackathon-Ricons-D304-feature-GiangHoang/K4-Hackathon-Ricons-D304-feature-GiangHoang/codebase/slides_work/slide-${i+1}.png`);
await save(await p.export({ format: 'webp', montage: true, scale: 1 }), 'C:/Users/Admin/Downloads/K4-Hackathon-Ricons-D304-feature-GiangHoang/K4-Hackathon-Ricons-D304-feature-GiangHoang/codebase/slides_work/montage.webp');
const pptx = await PresentationFile.exportPptx(p); await pptx.save(OUT);
