package lab

import (
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin/binding"
)

// StrictJSON is a local binder: no process-global decoder switches or test races.
// ShouldBindJSON is convenient, but its default binder does not reject extra JSON values.
type StrictJSON struct{}

func (StrictJSON) Name() string { return "strict-json" }
func (StrictJSON) Bind(r *http.Request, out any) error {
	media, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" {
		return problem(415, "unsupported_media_type", "use application/json")
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	// Streaming policy: return the decoder-observed first error; invalid oversized
	// input may be 400. Map 413 only when Decode returns a MaxBytesError. Do not drain.
	fail := func(err error) error {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			return problem(413, "body_too_large", "body exceeds 256 bytes")
		}
		return problem(400, "invalid_json", "exactly one JSON object required")
	}
	if err := decoder.Decode(out); err != nil {
		return fail(err)
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		if err != nil {
			return fail(err)
		}
		return fail(errors.New("extra JSON"))
	}
	input, ok := out.(*Input)
	if !ok {
		return problem(500, "internal_error", "internal service error")
	}
	input.SKU = strings.TrimSpace(input.SKU)
	if err := binding.Validator.ValidateStruct(input); err != nil {
		return problem(422, "invalid_input", "sku and quantity do not satisfy the contract")
	}
	return nil
}
