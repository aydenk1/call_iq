const rawApiBaseUrl =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

const apiBaseUrl = rawApiBaseUrl.replace(/\/$/, "");

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const url = `${apiBaseUrl}/calls/${encodeURIComponent(id)}/status`;
  const body = await request.text();

  try {
    const response = await fetch(url, {
      method: "PATCH",
      headers: {
        "Content-Type": request.headers.get("content-type") ?? "application/json",
      },
      body,
    });

    const responseBody = await response.text();
    return new Response(responseBody, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("Status update proxy error", error);
    return new Response("Failed to reach API", { status: 502 });
  }
}
