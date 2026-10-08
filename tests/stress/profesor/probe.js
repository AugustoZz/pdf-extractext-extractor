import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 1, iterations: 1, thresholds: { checks: ['rate==1'] } };
const names = [
    '2020-Scrum-Guide-Spanish-Latin-South-American.pdf',
    'Essential-Kanban-Condensed-Spanish.pdf',
    'Filosofia Lean.pdf',
    'scrum_manager_historias_usuario.pdf',
];
const pdfs = names.map((name) => open(`/stress/pdfs/${name}`, 'b'));
export default function () {
    const health = http.get('https://extract.universidad.localhost/health');
    if (!check(health, { 'TLS health 200': (r) => r.status === 200 })) throw new Error(`TLS/host failed: ${health.error}`);
    console.log(JSON.stringify({ endpoint: health.url, status: health.status, protocol: health.proto, tls: health.tls_version }));
    for (let i = 0; i < pdfs.length; i++) {
        const response = http.post('https://extract.universidad.localhost/extract', pdfs[i], { headers: { 'Content-Type': 'application/pdf' } });
        if (!check(response, {
            'PDF status and contract': (r) => {
                if (r.status !== 200) return false;
                try {
                    const body = r.json();
                    return body.page_count === [16, 90, 42, 62][i] && typeof body.content === 'string' && body.content.length > 0;
                } catch (_) { return false; }
            },
        })) throw new Error(`PDF failed: ${names[i]}`);
        console.log(JSON.stringify({ pdf: names[i], pages: response.json().page_count, characters: response.json().content.length }));
    }
    const host = http.get('http://host.docker.internal:8080/health');
    if (!check(host, { 'HTTP host health 200': (r) => r.status === 200 })) throw new Error('Published host port 8080 failed');
    console.log(JSON.stringify({ endpoint: host.url, status: host.status }));
}
