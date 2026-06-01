import { GITHUB_URL } from "../constants"

/** One-line open-source note. */
export function OpenSourceSection() {
  return (
    <p className="openSourceLine container">
      Apache-2.0 open source —{" "}
      <a href={GITHUB_URL} target="_blank" rel="noreferrer">
        fork it on GitHub
      </a>{" "}
      if you want your own flavor.
    </p>
  )
}
