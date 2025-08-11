#===============================================================================
# 참조 모듈 목록.
#===============================================================================
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response
from typing import Generator, Optional, Tuple
import os
from http import HTTPStatus


#===============================================================================
# 전역 변수 목록.
#===============================================================================
videoDirectory = os.environ.get("VS_FILE_DIRECTORY", "/videos")
streamingChunkSize = int(os.environ.get("VS_STREAMING_CHUNKSIZE", 1024 * 1024))
exampleVideoPath = f"{videoDirectory}/sample.mp4"
app = FastAPI()


#===============================================================================
# 바이트 범위 가져오기.
# - 서버에 요청시 반드시 헤더는 다음의 형태. (RFC 7233 (HTTP/1.1 Range Requests))
# - 1. Range: bytes={start}-{end}
# - 2. Range: bytes={start}-
# - 3. Range: bytes=-{end}
#===============================================================================
def GetByteRange(range: str) -> Optional[Tuple[int, int]]:
	if range is None:
		return None

	units, range_spec = range.strip().split("=")
	if units != "bytes":
		raise HTTPException(status_code=HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, detail="Only 'bytes' range supported")

	start_str, end_str = range_spec.split("-")
	start = int(start_str)
	end = int(end_str) if end_str else None
	return (start, end)


#===============================================================================
# 파일 스트림 열기. (제너레이터 함수)
# - 실제 파일을 열어 특정 범위의 바이트 배열을 매 루프마다 반환.
#===============================================================================
def OpenFileStream(videoFilePath: str, startIndex: int, endIndex: Optional[int]) -> Generator[bytes, None, None]:
	with open(videoFilePath, "rb") as file:
		file.seek(startIndex)
		while True:
			bytes_to_read = streamingChunkSize if endIndex is None else min(streamingChunkSize, endIndex - startIndex + 1)
			if bytes_to_read <= 0:
				break
			data = file.read(bytes_to_read)
			if not data:
				break
			startIndex += len(data)
			yield data


#===============================================================================
# 재생 요청.
#===============================================================================
@app.get("/play")
async def OnRequestPlay(request: Request) -> Response:

	# 파일 아이디. (임시)
	fileID = request.get("ID")

	# 요청 범위.
	range = request.headers.get("Range")
	isMultiple = range.find(",") != -1

	# 파일 검사.
	if not os.path.exists(exampleVideoPath):
		raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="File not found")
	
	# 범위 얻어오기.
	fileSize = os.path.getsize(exampleVideoPath)
	byteRange = GetByteRange(range)
	headers = {
		"Content-Type": "video/mp4",
		"Accept-Ranges": "bytes",
	}

	# 범위가 없을 경우.
	if not byteRange:
		# 전체 반환.
		headers["Content-Length"] = str(fileSize),
		bytesGenerator = OpenFileStream(exampleVideoPath, 0, None)
		return StreamingResponse(bytesGenerator, status_code=HTTPStatus.OK, headers=headers)

	# 부분 범위일 경우.
	start, end = byteRange
	end = end if end is not None else fileSize - 1

	# 파일 범위에서 벗어난 인덱스가 지정됨.
	if start >= fileSize or end >= fileSize:
		raise HTTPException(status_code=HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, detail="Range Not Satisfiable")

	# 범위 반환.
	headers["Content-Range"] = f"bytes {start}-{end}/{fileSize}"
	headers["Content-Length"] = str(end - start + 1)
	bytesGenerator = OpenFileStream(exampleVideoPath, start, end)
	return StreamingResponse(bytesGenerator, status_code=HTTPStatus.PARTIAL_CONTENT, headers=headers)