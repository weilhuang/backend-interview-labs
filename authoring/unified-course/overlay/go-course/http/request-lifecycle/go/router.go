package lab

import (
	"encoding/json"
	"net/http"
	"time"
)

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	// A response can already be committed; logging/metrics may observe an encode/write error,
	// but writing a second error response here would corrupt the first response.
	_ = json.NewEncoder(w).Encode(body)
}
func writeProblem(w http.ResponseWriter, p *Problem) {
	var body ErrorBody
	body.Error.Code = p.Code
	body.Error.Message = p.Message
	writeJSON(w, p.Status, body)
}
func NewHandler(store Store, budget time.Duration) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("POST /orders", CreateHandler(store, budget))
	return mux
}
