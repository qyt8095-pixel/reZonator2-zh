#ifndef HEADLESS_RUNNER_H
#define HEADLESS_RUNNER_H

/**
    Headless batch evaluation mode (--headless).

    Reads one JSON request from stdin (see rezonator2-phase1-protocol.md),
    evaluates it with the application's own SchemaReaderJson +
    RoundTripCalculator / BeamCalculator math (the same code the UI uses),
    and writes one JSON result object to stdout.

    Exit codes:
      0 - request processed (individual mutation failures are reported
          per-result inside the JSON, they do not change the exit code).
      1 - base_schema failed to load, or the schema has no active elements,
          or no beam calculator could be created.
      2 - malformed request JSON (not an object, missing base_schema, ...).
    On exit codes 1 and 2 stdout is empty and the reason goes to stderr.
*/
int runHeadless();

#endif // HEADLESS_RUNNER_H
