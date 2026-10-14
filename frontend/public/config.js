// Endereco do API Gateway que o navegador chama.
// No container, o nginx responde /config.js no lugar deste arquivo, com o valor
// da variavel API_URL (ver nginx/default.conf.template). Sem valor aqui, o
// frontend usa o mesmo host da pagina na porta 8000 (desenvolvimento local).
window.API_URL = window.API_URL || "";
