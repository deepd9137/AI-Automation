import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const backendRes = await fetch(`${BACKEND}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await backendRes.json();
  if (!backendRes.ok) {
    return NextResponse.json(data, { status: backendRes.status });
  }

  const setCookieHeader = backendRes.headers.get("set-cookie");
  const response = NextResponse.json(data);

  if (setCookieHeader) {
    // Forward the httpOnly refresh_token cookie from the backend
    response.headers.set("set-cookie", setCookieHeader);
  }

  return response;
}
