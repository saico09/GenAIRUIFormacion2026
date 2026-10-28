"""Envía las trazas locales a Phoenix sin esperar al exportador en cada petición."""

import json
import os
from functools import wraps

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

tracer = trace.get_tracer("genai.rag")


def configure_tracing() -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({
        "service.name": "python-api",
        "openinference.project.name": "genai",
    }))
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://phoenix:6006/v1/traces"),
        timeout=5,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def trace_node(*input_keys: str, kind: str = "CHAIN", attributes: dict | None = None):
    """Un span por nodo, con su entrada necesaria y la actualización que devuelve."""
    def decorate(function):
        @wraps(function)
        def wrapped(state):
            values = {key: state[key] for key in input_keys}
            with tracer.start_as_current_span(function.__name__, attributes={
                "openinference.span.kind": kind,
                "request_id": state["request_id"],
                "input.value": json.dumps(values, ensure_ascii=False),
                "input.mime_type": "application/json",
                **(attributes or {}),
            }) as span:
                result = function(state)
                span.set_attributes({"output.value": json.dumps(result, ensure_ascii=False),
                                     "output.mime_type": "application/json"})
                span.set_status(trace.StatusCode.OK)
                return result
        return wrapped
    return decorate
