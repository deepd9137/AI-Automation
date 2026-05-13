import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("refresh_token")?.value;

  const backendRes = await fetch(`${BACKEND}/auth/refresh`, {
    method: "POST",
    headers: refreshToken ? { Cookie: `refresh_token=${refreshToken}` } : {},
  });

  const data = await backendRes.json();
  if (!backendRes.ok) {
    return NextResponse.json(data, { status: backendRes.status });
  }

  const setCookieHeader = backendRes.headers.get("set-cookie");
  const response = NextResponse.json(data);

  if (setCookieHeader) {
    response.headers.set("set-cookie", setCookieHeader);
  }

  return response;
}
