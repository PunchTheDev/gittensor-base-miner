object App {
  def main(args: Array[String]): Unit =
    throw new RuntimeException("boom before binding HTTP server")
}